"""AI 检索与治理规则 —— 专项测试。

**重点不是"AI 能不能回答问题"，而是治理规则有没有被真正执行。**

验证七项：

  1 引用必填     —— has_citation=False 时前端不应展示
  2 四段式强制   —— 结论/依据/不确定性/责任声明
  3 权限隔离     —— 只检索用户有权查看的内容，且过滤发生在检索之前
  4 只索引已发布 —— 草稿与审批中的内容不进知识库
  5 会话限项目   —— 跨项目继续会话必须被拒
  6 降级要诚实   —— 未配置模型时不编造答案，只给检索原文
  7 引用可溯源   —— 引用带文件版本与页码表号，能回到原文

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/test_ai.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSWORD = "Tjad@2026"

passed = 0
failed = 0
_tokens: dict[str, str] = {}


def check(desc: str, cond: bool, extra: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {desc}")
    else:
        failed += 1
        print(f"  [FAIL] {desc}  {extra}")


def login(client: TestClient, username: str) -> dict:
    if username not in _tokens:
        r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, f"{username} 登录失败: {r.text[:200]}"
        _tokens[username] = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {_tokens[username]}"}


def main() -> int:
    client = TestClient(app)
    h_ou = login(client, "ouyuxin")
    h_zw = login(client, "chenkaili")   # 张伟已不在演示账号中，改用建设单位
    h_li = login(client, "ligong")

    # ---------- 准备 ----------
    print("\n[0] 准备：项目与已发布文档")
    r = client.get("/api/v1/projects", headers=h_ou)
    hz = next((p for p in r.json()["data"] if "杭州" in p["name"]), None)
    check("找到杭州项目", hz is not None)
    if not hz:
        return 1
    pid = hz["id"]

    # 苏州项目用于跨项目越权测试
    r = client.get("/api/v1/projects", headers=h_ou)
    all_projs = r.json()["data"]
    other = next((p for p in all_projs if p["id"] != pid), None)
    check("找到另一个项目（用于跨项目测试）", other is not None)

    # ---------- 提供方状态 ----------
    print("\n[1] 提供方状态（未配置模型时的诚实提示）")
    r = client.get("/api/v1/ai/provider-status", headers=h_ou)
    check("提供方状态接口可访问", r.status_code == 200, f"got {r.status_code}")
    st = r.json()["data"]
    check("返回 mode 字段", "mode" in st, str(st))
    check("返回 available 字段", "available" in st, str(st))
    check("返回日志保留天数", st.get("log_retention_days", 0) >= 90, str(st))
    check("未配置模型时 available=False（诚实降级）",
          st["available"] is False, str(st))
    check("未配置时给出说明文字", bool(st.get("note")), str(st))

    # ---------- 索引已发布版本 ----------
    print("\n[2] 只允许已发布版本进入知识库")
    r = client.get(f"/api/v1/projects/{pid}/documents", headers=h_ou)
    docs = r.json()["data"]
    check("取到文档列表", len(docs) > 0, f"got {len(docs)}")

    # 列表接口默认不返回版本，逐份取版本
    all_versions: list[dict] = []
    for d in docs:
        rv = client.get(f"/api/v1/documents/{d['id']}/versions", headers=h_ou)
        if rv.status_code == 200:
            all_versions.extend(rv.json()["data"])

    draft_version_id = next(
        (v["id"] for v in all_versions if v["state"] in ("DRAFT", "CHECKING", "REVIEWING")),
        None,
    )
    published_version_id = next(
        (v["id"] for v in all_versions if v["state"] == "PUBLISHED"), None
    )

    check("找到已发布版本", published_version_id is not None,
          str([v["state"] for v in all_versions]))
    check("找到未发布版本", draft_version_id is not None,
          str([v["state"] for v in all_versions]))

    if draft_version_id:
        r = client.post(
            f"/api/v1/ai/projects/{pid}/knowledge/index",
            headers=h_ou,
            json={"version_id": draft_version_id},
        )
        check("索引未发布版本 → 被拒绝", r.status_code == 400,
              f"got {r.status_code} {r.text[:200]}")
        if r.status_code == 400:
            check("拒绝原因说明只有已发布能入库",
                  "已发布" in r.json()["message"], r.json().get("message"))

    if published_version_id:
        r = client.post(
            f"/api/v1/ai/projects/{pid}/knowledge/index",
            headers=h_ou,
            json={"version_id": published_version_id},
        )
        check("索引已发布版本成功", r.status_code == 200,
              f"got {r.status_code} {r.text[:200]}")
        if r.status_code == 200:
            check("返回索引块数", r.json()["data"]["chunk_count"] > 0,
                  str(r.json()["data"]))

    # 索引全部已发布版本，让后续检索有内容
    indexed = 0
    for v in all_versions:
        if v["state"] == "PUBLISHED":
            r = client.post(
                f"/api/v1/ai/projects/{pid}/knowledge/index",
                headers=h_ou,
                json={"version_id": v["id"]},
            )
            if r.status_code == 200:
                indexed += 1
    print(f"    (已索引 {indexed} 个已发布版本)")
    check("至少索引了若干版本", indexed > 0, str(indexed))

    # ---------- 仅检索（不走模型） ----------
    print("\n[3] 仅检索：过滤发生在检索之前")
    r = client.get(
        f"/api/v1/ai/projects/{pid}/retrieve",
        headers=h_ou,
        params={"q": "桩基 承载力 勘察"},
    )
    check("仅检索接口可访问", r.status_code == 200, f"got {r.status_code}")
    hits = r.json()["data"]
    check("检索有结果", len(hits) > 0, f"got {len(hits)}")
    if hits:
        h0 = hits[0]
        check("检索结果带定位串", bool(h0.get("locator")), str(h0.keys()))
        check("检索结果带原文片段", bool(h0.get("quoted_text")), str(h0.keys()))
        check("检索结果带相关性分数", h0.get("score") is not None, str(h0.keys()))

    # 检索不到的词 → 空结果
    r = client.get(
        f"/api/v1/ai/projects/{pid}/retrieve",
        headers=h_ou,
        params={"q": "zzz不存在的关键词qqq"},
    )
    check("无关关键词返回空结果", r.json()["data"] == [],
          str(r.json()["data"])[:80])

    # ---------- 提问（降级模式） ----------
    print("\n[4] 提问：降级模式不编造答案")
    r = client.post(
        f"/api/v1/ai/projects/{pid}/ask",
        headers=h_ou,
        json={"question": "桩基承载力与勘察报告的关系是什么？"},
    )
    check("提问接口可访问", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")
    ans = r.json()["data"]

    check("返回会话 id", bool(ans["conversation_id"]), str(ans.keys()))
    check("返回消息 id", bool(ans["message_id"]), str(ans.keys()))
    check("标记为降级模式", ans["degraded"] is True, str(ans["degraded"]))
    check("给出降级原因", bool(ans["degrade_reason"]), str(ans.get("degrade_reason")))

    # 四段式
    check("含【结论】", bool(ans.get("conclusion")), str(ans.get("conclusion"))[:60])
    check("含【依据】", bool(ans.get("basis")), str(ans.get("basis"))[:60])
    check("含【不确定性】", bool(ans.get("uncertainty")), str(ans.get("uncertainty"))[:60])
    check("含【责任声明】", bool(ans.get("disclaimer")), str(ans.get("disclaimer"))[:60])
    check("责任声明包含免责表述",
          "复核" in (ans.get("disclaimer") or ""), str(ans.get("disclaimer")))

    # 引用
    check("有引用（检索到内容）", ans["has_citation"] is True, str(ans["has_citation"]))
    check("引用列表非空", len(ans["citations"]) > 0, str(len(ans["citations"])))
    if ans["citations"]:
        c0 = ans["citations"][0]
        check("引用带定位串", bool(c0.get("locator")), str(c0.keys()))
        check("引用带原文片段", bool(c0.get("quoted_text")), str(c0.keys()))
        check("引用带源版本 id", bool(c0.get("source_version_id")), str(c0.keys()))

    # 降级回答必须提到"未配置"
    check("降级回答明确说明未配置模型",
          "未配置" in (ans.get("conclusion") or ""), str(ans.get("conclusion"))[:80])

    conv_id = ans["conversation_id"]

    # ---------- 会话消息 ----------
    print("\n[5] 会话消息与引用")
    r = client.get(f"/api/v1/ai/conversations/{conv_id}/messages", headers=h_ou)
    check("会话消息接口可访问", r.status_code == 200, f"got {r.status_code}")
    msgs = r.json()["data"]
    check("会话含用户消息与回答", len(msgs) >= 2, f"got {len(msgs)}")
    if len(msgs) >= 2:
        check("第一条是用户消息", msgs[0]["role"] == "user", msgs[0].get("role"))
        check("第二条是回答", msgs[1]["role"] == "assistant", msgs[1].get("role"))
        check("回答带引用", len(msgs[1]["citations"]) > 0, str(len(msgs[1]["citations"])))
        check("回答带四段字段",
              bool(msgs[1].get("conclusion")) and bool(msgs[1].get("uncertainty")),
              str(msgs[1].keys()))

    r = client.get(f"/api/v1/ai/projects/{pid}/conversations", headers=h_ou)
    check("会话列表可访问", r.status_code == 200, f"got {r.status_code}")
    check("会话列表含刚才的会话",
          any(c["id"] == conv_id for c in r.json()["data"]), str(len(r.json()["data"])))

    # ---------- 反馈 ----------
    print("\n[6] 反馈")
    mid = ans["message_id"]
    r = client.post(
        f"/api/v1/ai/messages/{mid}/feedback",
        headers=h_ou,
        json={"feedback": "USEFUL", "note": "引用很有用"},
    )
    check("提交有用反馈成功", r.status_code == 200, f"got {r.status_code}")

    r = client.post(
        f"/api/v1/ai/messages/{mid}/feedback",
        headers=h_ou,
        json={"feedback": "MAYBE"},
    )
    check("非法反馈值 → 被拒绝", r.status_code == 400, f"got {r.status_code}")

    # 别人不能给我的消息反馈
    r = client.post(
        f"/api/v1/ai/messages/{mid}/feedback",
        headers=h_zw,
        json={"feedback": "USELESS"},
    )
    check("他人不能对别人的会话反馈 → 被拒绝", r.status_code == 403,
          f"got {r.status_code}")

    # ---------- 会话限项目 ----------
    print("\n[7] 会话严格限定在当前项目")
    if other:
        # 拿杭州项目的会话去苏州项目提问 → 必须被拒
        r = client.post(
            f"/api/v1/ai/projects/{other['id']}/ask",
            headers=h_ou,
            json={"question": "继续上个问题", "conversation_id": conv_id},
        )
        check("跨项目继续会话 → 被拒绝", r.status_code == 403,
              f"got {r.status_code} {r.text[:200]}")
        if r.status_code == 403:
            check("拒绝原因说明会话属于其他项目",
                  "其他项目" in r.json()["message"] or "跨项目" in r.json()["message"],
                  r.json().get("message"))

        # 别人的会话也看不到
        r = client.get(f"/api/v1/ai/conversations/{conv_id}/messages", headers=h_zw)
        check("他人不能查看我的会话 → 被拒绝",
              r.status_code in (403, 404), f"got {r.status_code}")

    # ---------- 权限隔离 ----------
    print("\n[8] 权限隔离：非项目参与人被拦住")
    if other:
        r = client.post(
            f"/api/v1/ai/projects/{other['id']}/ask",
            headers=h_li,
            json={"question": "这个项目的桩基参数是多少"},
        )
        check("非项目参与人提问 → 被拒绝", r.status_code == 403,
              f"got {r.status_code} {r.text[:200]}")

        r = client.get(
            f"/api/v1/ai/projects/{other['id']}/retrieve",
            headers=h_li,
            params={"q": "桩基"},
        )
        check("非项目参与人检索 → 被拒绝", r.status_code == 403, f"got {r.status_code}")

    # ---------- 敏感等级过滤 ----------
    print("\n[9] 敏感等级过滤（权限过滤在检索之前）")
    # 勘察报告是 RESTRICTED 级。设计人有 EDIT 权限 → 上限 RESTRICTED，能检索到
    r = client.get(
        f"/api/v1/ai/projects/{pid}/retrieve",
        headers=h_ou,
        params={"q": "勘察报告 详勘"},
    )
    check("设计人可检索（含受限级）", r.status_code == 200, f"got {r.status_code}")
    ou_hits = r.json()["data"]

    # 王五（监理，只有 VIEW 权限）→ 上限 INTERNAL，受限级内容应被过滤掉
    h_wang = login(client, "wangwu")
    r = client.get(
        f"/api/v1/ai/projects/{pid}/retrieve",
        headers=h_wang,
        params={"q": "勘察报告 详勘"},
    )
    check("监理可访问检索接口（是项目参与人）", r.status_code == 200, f"got {r.status_code}")
    wang_hits = r.json()["data"]

    print(f"    (设计人检索到 {len(ou_hits)} 条，监理检索到 {len(wang_hits)} 条)")
    check("监理检索结果不多于设计人（受限级被过滤）",
          len(wang_hits) <= len(ou_hits),
          f"{len(wang_hits)} vs {len(ou_hits)}")

    # ---------- 知识库跨项目共享 ----------
    print("\n[10] 跨项目知识库（刻意共享的经验）")
    r = client.post(
        f"/api/v1/ai/projects/{pid}/ask",
        headers=h_ou,
        json={"question": "地铁保护区桩型如何选择？", "include_knowledge_base": True},
    )
    check("提问（含知识库）成功", r.status_code == 200, f"got {r.status_code}")
    ans_kb = r.json()["data"]

    kb_cites = [c for c in ans_kb["citations"] if c.get("source_type") == "KNOWLEDGE_BASE"]
    print(f"    (引用 {len(ans_kb['citations'])} 条，其中知识库 {len(kb_cites)} 条)")
    check("能检索到跨项目知识库内容（地铁保护区经验）",
          len(kb_cites) > 0, str([c.get("locator") for c in ans_kb["citations"]]))

    r = client.post(
        f"/api/v1/ai/projects/{pid}/ask",
        headers=h_ou,
        json={"question": "地铁保护区桩型如何选择？", "include_knowledge_base": False},
    )
    check("关闭知识库后提问成功", r.status_code == 200, f"got {r.status_code}")
    ans_nokb = r.json()["data"]
    kb_cites2 = [c for c in ans_nokb["citations"] if c.get("source_type") == "KNOWLEDGE_BASE"]
    check("关闭知识库后不再引用知识库内容", len(kb_cites2) == 0, str(len(kb_cites2)))

    # ---------- 空问题 ----------
    print("\n[11] 参数校验")
    r = client.post(
        f"/api/v1/ai/projects/{pid}/ask",
        headers=h_ou,
        json={"question": ""},
    )
    check("空问题 → 被拒绝", r.status_code == 422 or r.status_code == 400,
          f"got {r.status_code}")

    # ---------- 汇总 ----------
    print("\n" + "=" * 56)
    print(f"通过 {passed} 项，失败 {failed} 项")
    if failed == 0:
        print()
        print("提示：测试会往知识库写入切片、并创建 AI 会话。")
        print("      需要干净演示数据时执行：")
        print("        .venv\\Scripts\\python.exe -m app.seed.seed_all --reset")
    print("=" * 56)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
