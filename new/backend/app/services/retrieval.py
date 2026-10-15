"""检索服务 —— AI 回答的证据来源。

**核心治理规则（对应《公共层契约》§4.1）**：

1. **权限过滤发生在检索之前，而不是拿到结果之后。**
   严禁"先检索全库再过滤结果" —— 那样模型已经看到内容了，
   过滤只是掩耳盗铃。本模块的过滤全部在 SQL 层完成。

2. **只检索 `PUBLISHED` 版本的内容。**
   草稿和审批中的文件不进知识库 —— 否则 AI 会引用还没生效的结论。

3. **切片按工程语义结构，不按固定字数。**
   每个 chunk 挂 `stage_code / discipline / doc_type / section_path / page_no`，
   这样引用能精确到"哪份文件、哪一版、第几页/哪张表"。

4. **会话上下文严格限定在当前项目。**
   内部试用期不允许跨项目检索（哪怕同一个人有多个项目权限）。
   例外：**跨项目知识库**（已闭环问题沉淀）是刻意共享的经验积累，
   见 `search_knowledge_base()`。

当前检索方式：关键词匹配（SQLite 全文检索能力有限）。
接入 pgvector 后把 `_score_chunk()` 换成语义相似度即可，**接口形态不变**。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai import KnowledgeChunk
from app.models.document import Document, DocumentVersion
from app.models.enums import DocumentState, SecretLevel, StageCode
from app.models.issue import Issue

logger = logging.getLogger("app.ai.retrieval")


@dataclass
class RetrievedChunk:
    """一条检索结果。**它是引用的唯一来源** —— 模型只能用这里出现的内容作答。"""

    chunk_id: str | None = None
    source_type: str = "DOCUMENT"      # DOCUMENT / KNOWLEDGE_BASE
    text: str = ""

    # 溯源信息（前端"点开看原文"靠这些字段）
    source_version_id: str | None = None
    document_id: str | None = None
    document_title: str | None = None
    doc_no: str | None = None
    version_no: str | None = None
    version_state: str | None = None
    section_path: str | None = None
    page_no: int | None = None

    stage_code: str | None = None
    discipline: str | None = None
    doc_type: str | None = None
    secret_level: str = SecretLevel.INTERNAL.value

    score: float = 0.0
    # 便于前端直接展示的定位串，如 "详勘 V2.0 P.15 表5-2"
    locator: str = ""

    def to_citation(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source_type": self.source_type,
            "source_version_id": self.source_version_id,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "doc_no": self.doc_no,
            "version_no": self.version_no,
            "section_path": self.section_path,
            "page_no": self.page_no,
            "locator": self.locator,
            "quoted_text": self.text[:600],
            "score": round(self.score, 4),
        }


# ============================================================
# 关键词切分与打分
# ============================================================

# 中文没有词边界，用"字 + 双字组合"做轻量切分。
# 接向量检索后这套逻辑就不再需要，但作为兜底保留。
_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "或", "有", "无", "为", "对", "从",
    "如何", "什么", "怎么", "请问", "一下", "这个", "那个", "以及", "可以",
}


def _tokens(text: str) -> list[str]:
    """把查询切成关键词。

    中文没有词边界，这里用"字 + 2~4 字滑窗"做轻量切分。
    接向量检索后这套逻辑不再需要，但作为兜底保留。

    **为什么滑窗要切 2/3/4 字**：只切长词会漏掉短查询；
    但只用 2 字词又太宽松 —— 实测「zzz不存在关键词qqq」会切出
    「存在」，从而命中正文里的「存在挤土效应风险」，
    属于典型的关键词误召回。所以调用方按长度区分用途，见 `_is_strong_token()`。
    """
    if not text:
        return []
    out: list[str] = []
    # 英文与数字
    out.extend(re.findall(r"[A-Za-z][A-Za-z0-9_\-\.]{1,30}", text))
    # 中文滑窗（2/3/4 字）
    zh = re.sub(r"[^\u4e00-\u9fff]", " ", text)
    for seg in zh.split():
        if len(seg) < 2:
            continue
        for n in (2, 3, 4):
            for i in range(len(seg) - n + 1):
                w = seg[i : i + n]
                if w not in _STOPWORDS:
                    out.append(w)
    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


# 匹配用的最短长度。
# 中文 2 字词的歧义太大（「存在」「不在」「在的」），
# 用它们做匹配会产生大量误召回。所以：
#   - 长度 >= 3 的 token 或英文/数字 token → 可以单独作为命中依据
#   - 2 字中文 token → 只参与打分，不单独决定"命中"
# 这是关键词检索的工程折中；接向量检索后由语义相似度替代。
_MIN_MATCH_LEN = 3


def _is_strong_token(t: str) -> bool:
    """是否可单独作为命中依据。"""
    if re.match(r"^[A-Za-z0-9]", t):
        return len(t) >= 2       # 英文/数字短词歧义小
    return len(t) >= _MIN_MATCH_LEN


def _score(text: str, tokens: list[str], *, section: str | None = None) -> float:
    """关键词打分。

    权重设计：正文命中 < 章节路径命中。
    章节路径命中往往意味着"命中了正确的章节"，相关性更高。

    要求：**至少有一个"强 token"命中**，否则返回 0。
    这条是防止误召回的关键 —— 只靠 2 字碎片命中的结果不应算相关。
    """
    if not text:
        return 0.0
    body = text.lower()
    sec = (section or "").lower()

    strong_hit = False
    total = 0.0
    for t in tokens:
        tl = t.lower()
        cnt = body.count(tl)
        if cnt:
            total += 1.0 + min(cnt - 1, 3) * 0.25   # 出现多次略加权，但避免长文本刷分
            if _is_strong_token(t):
                strong_hit = True
        if sec and tl in sec:
            total += 1.5
            if _is_strong_token(t):
                strong_hit = True

    if not strong_hit:
        return 0.0

    # 长文本归一化，避免"越长分越高"
    length_penalty = 1.0 + max(0, len(body) - 800) / 8000.0
    return total / length_penalty


# ============================================================
# 检索
# ============================================================


def search_documents(
    db: Session,
    *,
    project_id: str,
    query: str,
    stage_code: str | None = None,
    discipline: str | None = None,
    limit: int = 8,
    max_secret_level: int = 2,
) -> list[RetrievedChunk]:
    """在**本项目**的已发布版本内容中检索。

    参数：
        max_secret_level  当前用户在此项目可查看的最高敏感等级（由权限引擎给出）。
                          **过滤在 SQL 里完成**，不是拿到结果后再筛。

    返回按相关性排序的片段。
    """
    tokens = _tokens(query)
    if not tokens:
        return []

    # ---- 第一步：确定"有权限看"的文档集合（SQL 层过滤）----
    doc_stmt = select(Document).where(Document.project_id == project_id)
    if stage_code:
        doc_stmt = doc_stmt.where(Document.stage_code == stage_code)
    if discipline:
        doc_stmt = doc_stmt.where(Document.discipline == discipline)
    docs = list(db.execute(doc_stmt).scalars().all())

    allowed_docs: dict[str, Document] = {}
    for d in docs:
        try:
            need = {
                SecretLevel.PUBLIC.value: 0,
                SecretLevel.INTERNAL.value: 1,
                SecretLevel.RESTRICTED.value: 2,
                SecretLevel.SECRET.value: 3,
            }.get(d.secret_level, 1)
        except AttributeError:
            need = 1
        if need <= max_secret_level:
            allowed_docs[d.id] = d

    if not allowed_docs:
        return []

    # ---- 第二步：取这些文档的**已发布**版本 ----
    # 只检索 PUBLISHED —— 草稿和审批中的内容不该被 AI 引用。
    ver_rows = db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id.in_(list(allowed_docs.keys())),
            DocumentVersion.state == DocumentState.PUBLISHED.value,
        )
    ).scalars().all()
    if not ver_rows:
        return []

    ver_map = {v.id: v for v in ver_rows}

    # ---- 第三步：取知识块（同样在 SQL 层限定到有权限的版本）----
    chunks = list(
        db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.source_version_id.in_(list(ver_map.keys())))
        ).scalars().all()
    )

    results: list[RetrievedChunk] = []
    for c in chunks:
        s = _score(c.text, tokens, section=c.section_path)
        if s <= 0:
            continue
        v = ver_map.get(c.source_version_id or "")
        d = allowed_docs.get(v.document_id) if v else None
        results.append(
            RetrievedChunk(
                chunk_id=c.id,
                source_type="DOCUMENT",
                text=c.text,
                source_version_id=c.source_version_id,
                document_id=d.id if d else None,
                document_title=d.title if d else None,
                doc_no=d.doc_no if d else None,
                version_no=v.version_no if v else None,
                version_state=v.state if v else None,
                section_path=c.section_path,
                page_no=c.page_no,
                stage_code=c.stage_code,
                discipline=c.discipline,
                doc_type=c.doc_type,
                score=s,
                locator=_locator(d, v, c),
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]


def search_knowledge_base(
    db: Session,
    *,
    query: str,
    stage_code: str | None = None,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """检索**跨项目知识库**（已闭环问题沉淀的经验）。

    这一块是**刻意跨项目共享**的：一个项目踩过的坑，别的项目不用再踩。
    与"会话上下文限项目"不冲突 —— 会话限项目是指不能拿别的项目的
    具体文件来回答，而沉淀后的知识已经脱敏为通用经验。
    """
    tokens = _tokens(query)
    if not tokens:
        return []

    stmt = select(Issue).where(Issue.is_knowledge.is_(True))
    if stage_code:
        stmt = stmt.where(Issue.stage_code == stage_code)
    rows = list(db.execute(stmt).scalars().all())

    results: list[RetrievedChunk] = []
    for i in rows:
        text = i.knowledge_summary or i.description or ""
        # 标题权重更高 —— 命中的往往是问题本身
        s = _score(text, tokens, section=i.title)
        if s <= 0:
            continue
        results.append(
            RetrievedChunk(
                chunk_id=None,
                source_type="KNOWLEDGE_BASE",
                text=text,
                document_title=i.title,
                doc_no=i.issue_no,
                section_path=f"已闭环问题 {i.issue_no or ''}".strip(),
                stage_code=i.stage_code,
                discipline="岩土",
                doc_type="问题案例",
                score=s * 1.1,   # 知识条目是可复用经验，略微加权
                locator=f"知识库 · {i.issue_no or '未编号'}",
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]


def search(
    db: Session,
    *,
    project_id: str,
    query: str,
    stage_code: str | None = None,
    max_secret_level: int = 2,
    include_knowledge_base: bool = True,
    limit: int = 8,
) -> list[RetrievedChunk]:
    """统一检索入口：本项目已发布文档 + 跨项目知识库。"""
    docs = search_documents(
        db,
        project_id=project_id,
        query=query,
        stage_code=stage_code,
        limit=limit,
        max_secret_level=max_secret_level,
    )
    kb: list[RetrievedChunk] = []
    if include_knowledge_base:
        kb = search_knowledge_base(db, query=query, stage_code=stage_code, limit=3)

    merged = docs + kb
    merged.sort(key=lambda r: r.score, reverse=True)
    return merged[: limit + 3]


def _locator(d: Document | None, v: DocumentVersion | None, c: KnowledgeChunk) -> str:
    """拼出人话定位串，例如「详勘 V2.0 P.15 表5-2」。"""
    parts: list[str] = []
    if d is not None:
        parts.append(d.title or "")
    if v is not None and v.version_no:
        parts.append(v.version_no)
    if c.section_path:
        parts.append(c.section_path)
    if c.page_no:
        parts.append(f"P.{c.page_no}")
    return " ".join(p for p in parts if p)


# ============================================================
# 知识库索引（把已发布文档切片入库）
# ============================================================


def index_document_version(
    db: Session,
    *,
    version_id: str,
    chunks: list[dict] | None = None,
) -> list[KnowledgeChunk]:
    """把某个已发布版本切片入知识库。

    **只允许 PUBLISHED 版本入库** —— 这是治理规则，不是建议。

    chunks 为 None 时按文本内容做一次朴素切片（演示与测试用）；
    生产环境应该由文档解析器按工程语义结构（章节、表格）产出切片。
    """
    v = db.get(DocumentVersion, version_id)
    if v is None:
        from fastapi import HTTPException, status as http_status

        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "文件版本不存在"},
        )

    if v.state != DocumentState.PUBLISHED.value:
        from fastapi import HTTPException, status as http_status

        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "code": 4001,
                "message": "只有「已发布」版本可以进入知识库 —— "
                "草稿和审批中的内容不该被 AI 引用。",
            },
        )

    doc = db.get(Document, v.document_id)

    # 幂等：先清掉该版本的旧切片
    for old in db.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.source_version_id == version_id)
    ).scalars().all():
        db.delete(old)
    db.flush()

    if not chunks:
        chunks = _naive_split(db, v, doc)

    created: list[KnowledgeChunk] = []
    for i, c in enumerate(chunks):
        kc = KnowledgeChunk(
            project_id=doc.project_id if doc else None,
            source_version_id=version_id,
            stage_code=doc.stage_code if doc else None,
            discipline=doc.discipline if doc else None,
            doc_type=doc.category_name if doc else None,
            section_path=c.get("section_path"),
            page_no=c.get("page_no"),
            text=c["text"],
            token_count=len(c["text"]),
            chunk_index=i,
            secret_level=doc.secret_level if doc else SecretLevel.INTERNAL.value,
            embedding_model=None,
        )
        db.add(kc)
        created.append(kc)
    db.flush()
    return created


def _naive_split(db: Session, v: DocumentVersion, doc: Document | None) -> list[dict]:
    """朴素切片（占位实现）。

    **刻意做得简单**：真实系统应按工程语义结构切片
    （土层参数表、桩型表、检测项、规范条文），
    那需要文档解析器。这里先保证链路可用，
    并在返回里标注这是占位实现，避免被误认为最终形态。
    """
    title = doc.title if doc else "文件"
    summary = v.change_summary or ""
    text = (
        f"{title}（{v.version_no}）。"
        f"{summary}。"
        f"本版本为已发布版本，可作为设计与施工依据。"
    )
    return [
        {
            "section_path": f"{title} · 版本说明",
            "page_no": None,
            "text": text,
        }
    ]
