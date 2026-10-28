"""问题管理与闭环 —— 专项测试。

重点验证三件事：

  1. **链路不可跳步**：必须先"分析识别"再"建议"，先"执行"再"验证"。
     跳步会让问题记录失去可追溯性 —— 这正是设计院最在意的。

  2. **闭环互锁**：没有"验证"节点就不允许闭环。
     "执行了"和"验证有效"是两件事，混在一起会让闭环变成走形式。

  3. **知识沉淀的前置条件**：只有已闭环的问题才能进知识库。
     未经验证的处理办法不该进入知识库，否则会把错误经验传播到后续项目。

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/test_issues.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

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


def add(client: TestClient, h: dict, pid: str, iid: str, action: str, content: str):
    return client.post(
        f"/api/v1/projects/{pid}/issues/{iid}/actions",
        headers=h,
        json={"action_type": action, "content": content},
    )


def main() -> int:
    client = TestClient(app)
    h_ou = login(client, "ouyuxin")
    # 签认人用建设单位陈铠俐 —— 张伟在新单位模型下不再是项目成员
    h_zw = login(client, "chenkaili")

    # ---------- 准备 ----------
    print("\n[0] 准备：项目与种子问题")
    r = client.get("/api/v1/projects", headers=h_ou)
    hz = next((p for p in r.json()["data"] if "杭州" in p["name"]), None)
    check("找到杭州项目", hz is not None)
    if not hz:
        return 1
    pid = hz["id"]

    r = client.get(f"/api/v1/projects/{pid}/issues", headers=h_ou)
    check("问题列表可访问", r.status_code == 200, f"got {r.status_code}")
    seeded = r.json()["data"]
    check("种子问题为 3 条", len(seeded) == 3, f"got {len(seeded)}")

    # 高危排前面
    if seeded:
        check("高危问题排在最前", seeded[0]["severity"] == "HIGH", seeded[0].get("severity"))
        check("列表带中文状态标签", bool(seeded[0].get("status_label")), str(seeded[0].get("status_label")))
        check("列表带中文来源标签", bool(seeded[0].get("source_label")), str(seeded[0].get("source_label")))

    # 种子里的已闭环问题应已沉淀
    closed_seed = next((s for s in seeded if s["status"] == "CLOSED"), None)
    check("存在已闭环的种子问题", closed_seed is not None)
    if closed_seed:
        check("已闭环问题标记为已沉淀知识", closed_seed["is_knowledge"] is True,
              str(closed_seed.get("is_knowledge")))
        check("已闭环问题带知识摘要", bool(closed_seed["knowledge_summary"]),
              str(closed_seed.get("knowledge_summary"))[:60])

    # ---------- 统计 ----------
    print("\n[1] 问题统计")
    r = client.get(f"/api/v1/projects/{pid}/issues/summary", headers=h_ou)
    check("统计接口可访问", r.status_code == 200, f"got {r.status_code}")
    s = r.json()["data"]
    check("统计总数正确", s["total"] == 3, str(s["total"]))
    check("统计已闭环数", s["closed"] == 1, str(s["closed"]))
    check("统计未闭环数", s["unclosed"] == 2, str(s["unclosed"]))
    check("统计高危数", s["high"] == 2, str(s["high"]))
    check("统计知识条目数", s["knowledge_count"] == 1, str(s["knowledge_count"]))

    # ---------- 新建问题 ----------
    print("\n[2] 提出问题")
    r = client.post(
        f"/api/v1/projects/{pid}/issues",
        headers=h_ou,
        json={
            "stage_code": "DESIGN",
            "title": "承台底面标高与地下水位关系需复核",
            "description": "承台底标高 -4.500，地下水位 -2.500，"
                           "需复核基坑降水与承台施工的可行性，以及抗浮验算是否覆盖。",
            "source": "REVIEW",
            "severity": "HIGH",
        },
    )
    check("提出问题返回 200", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")
    issue = r.json()["data"]
    iid = issue["id"]
    check("问题编号自动生成", (issue["issue_no"] or "").startswith("IS-"), str(issue.get("issue_no")))
    check("初始状态为待处理", issue["status"] == "OPEN", issue.get("status"))
    check("自动记录了问题描述环节", len(issue["actions"]) == 1, str(len(issue["actions"])))
    check("问题描述是链路第一步",
          issue["actions"][0]["action_type"] == "DESCRIBE",
          str(issue["actions"][0].get("action_type")))
    check("完成了 1/8 个环节", issue["completed_steps"] == 1, str(issue["completed_steps"]))
    check("总环节数为 8", issue["total_steps"] == 8, str(issue["total_steps"]))
    check("下一步允许查询", issue["available_actions"] == ["QUERY"], str(issue["available_actions"]))

    # ---------- 链路不可跳步 ----------
    print("\n[3] 链路不可跳步（核心规则）")

    # 跳过 QUERY 直接 ANALYZE
    r = add(client, h_ou, pid, iid, "ANALYZE", "直接分析")
    check("跳过「查询」直接「分析识别」→ 被拒绝", r.status_code == 400,
          f"got {r.status_code} {r.text[:200]}")
    if r.status_code == 400:
        check("拒绝原因说明要先完成「查询」",
              "查询" in r.json()["message"] and "跳步" in r.json()["message"],
              r.json().get("message"))

    # 跳过一堆直接 VERIFY
    r = add(client, h_ou, pid, iid, "VERIFY", "我直接验证了，已确认没有问题")
    check("直接跳到「验证」→ 被拒绝", r.status_code == 400, f"got {r.status_code}")
    if r.status_code == 400:
        check("拒绝原因列出了缺失的前置环节",
              "执行" in r.json()["message"], r.json().get("message"))

    # 直接 CLOSE
    r = add(client, h_ou, pid, iid, "CLOSE", "关闭")
    check("直接「闭环」→ 被拒绝", r.status_code == 400, f"got {r.status_code}")
    if r.status_code == 400:
        check("拒绝原因说明要先「验证」",
              "验证" in r.json()["message"], r.json().get("message"))

    # ---------- 按顺序走完链路 ----------
    print("\n[4] 按顺序走完八段式链路")

    r = add(client, h_ou, pid, iid, "QUERY",
            "检索规范 GB 50007-2011 §5.3 与浙江省地方标准，"
            "并查看本区域同类项目降水方案")
    check("记录「查询」成功", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    issue = r.json()["data"]
    check("查询带 AI 引用字段可用", "ai_citation" in issue["actions"][-1], str(issue["actions"][-1].keys()))
    check("状态推进为处理中", issue["status"] == "IN_PROGRESS", issue.get("status"))
    check("下一步允许分析识别", issue["available_actions"] == ["ANALYZE"], str(issue["available_actions"]))

    r = add(client, h_ou, pid, iid, "ANALYZE",
            "经复核，承台底位于地下水位以下 2.0m，原设计未考虑基坑降水引起的附加沉降，"
            "抗浮验算仅覆盖施工期未覆盖使用期。")
    check("记录「分析识别」成功", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    issue = r.json()["data"]
    check("下一步允许建议", issue["available_actions"] == ["SUGGEST"], str(issue["available_actions"]))

    r = add(client, h_ou, pid, iid, "SUGGEST",
            "建议：①承台底局部抬高至 -3.800；②增加抗浮锚杆 4 根/承台；"
            "③降水方案补充沉降监测点。依据：GB 50007-2011 §5.3.2、详勘 V2 P.8。")
    check("记录「建议」成功", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    issue = r.json()["data"]
    check("下一步允许执行", issue["available_actions"] == ["EXECUTE"], str(issue["available_actions"]))

    r = add(client, h_ou, pid, iid, "EXECUTE",
            "已按建议①③修改承台设计并更新桩基平面布置图，"
            "责任人欧雨欣，完成期限 2026-10-20。")
    check("记录「执行」成功", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    issue = r.json()["data"]
    check("下一步允许验证", issue["available_actions"] == ["VERIFY"], str(issue["available_actions"]))

    # 验证内容过短 → 被拒（防止走形式）
    r = add(client, h_ou, pid, iid, "VERIFY", "已确认")
    check("「验证」内容过短 → 被拒绝", r.status_code == 400, f"got {r.status_code}")
    if r.status_code == 400:
        check("拒绝原因强调验证要写清依据",
              "依据" in r.json()["message"] or "空话" in r.json()["message"],
              r.json().get("message"))

    r = add(client, h_zw, pid, iid, "VERIFY",
            "由建设单位复核：已核对修改后的承台图与抗浮计算书，"
            "抗浮安全系数由 0.96 提升至 1.12，满足 GB 50007-2011 要求，验证通过。")
    check("记录「验证」成功", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    issue = r.json()["data"]
    check("状态推进为待验证", issue["status"] == "PENDING_VERIFY", issue.get("status"))
    check("记录了验证人", bool(issue.get("verified_by")), str(issue.get("verified_by")))
    check("记录了验证结论", bool(issue.get("verify_conclusion")), str(issue.get("verify_conclusion"))[:60])
    check("下一步允许闭环", issue["available_actions"] == ["CLOSE"], str(issue["available_actions"]))

    # ---------- 闭环 ----------
    print("\n[5] 闭环")
    r = add(client, h_ou, pid, iid, "CLOSE",
            "验证有效，修改后的设计已发布，问题闭环。")
    check("闭环成功", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    issue = r.json()["data"]
    check("状态变为已闭环", issue["status"] == "CLOSED", issue.get("status"))
    check("记录了闭环时间", issue["closed_at"] is not None, str(issue.get("closed_at")))
    check("自动生成了知识摘要", bool(issue["knowledge_summary"]),
          str(issue.get("knowledge_summary"))[:80])
    check("知识摘要含问题与分析",
          "【问题】" in (issue["knowledge_summary"] or "")
          and "【分析】" in (issue["knowledge_summary"] or ""),
          str(issue.get("knowledge_summary"))[:100])
    check("知识摘要含验证结果",
          "【验证结果】" in (issue["knowledge_summary"] or ""),
          str(issue.get("knowledge_summary"))[:100])
    check("已完成 7/8 环节（未沉淀）", issue["completed_steps"] == 7, str(issue["completed_steps"]))
    check("闭环后下一步只剩知识沉淀",
          issue["available_actions"] == ["KNOWLEDGE"], str(issue["available_actions"]))

    # 闭环后不能再加处理记录
    r = add(client, h_ou, pid, iid, "EXECUTE", "再执行一次")
    check("已闭环后不能再加处理记录 → 被拒绝", r.status_code == 400, f"got {r.status_code}")
    if r.status_code == 400:
        check("拒绝原因提示应新建问题而非续写",
              "新建问题" in r.json()["message"], r.json().get("message"))

    # ---------- 知识沉淀前置条件 ----------
    print("\n[6] 知识沉淀的前置条件")

    # 未闭环的问题不能沉淀（用种子里"待验证"的那条）
    pending = next(
        (s for s in seeded if s["status"] == "PENDING_VERIFY"),
        None,
    )
    check("找到未闭环的问题", pending is not None, str([s["status"] for s in seeded]))
    if pending:
        r = client.post(
            f"/api/v1/projects/{pid}/issues/{pending['id']}/consolidate",
            headers=h_ou,
            json={},
        )
        check("未闭环问题沉淀知识 → 被拒绝", r.status_code == 400, f"got {r.status_code}")
        if r.status_code == 400:
            check("拒绝原因说明只有已闭环才能沉淀",
                  "闭环" in r.json()["message"], r.json().get("message"))

    # 已闭环的可以沉淀
    r = client.post(
        f"/api/v1/projects/{pid}/issues/{iid}/consolidate",
        headers=h_ou,
        json={},
    )
    check("已闭环问题沉淀成功", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")
    issue = r.json()["data"]
    check("标记为已沉淀知识", issue["is_knowledge"] is True, str(issue.get("is_knowledge")))
    check("完成 8/8 环节", issue["completed_steps"] == 8, str(issue["completed_steps"]))
    check("沉淀后无可用动作", issue["available_actions"] == [], str(issue["available_actions"]))

    # 重复沉淀 → 被拒
    r = client.post(
        f"/api/v1/projects/{pid}/issues/{iid}/consolidate",
        headers=h_ou,
        json={},
    )
    check("重复沉淀 → 被拒绝", r.status_code == 400, f"got {r.status_code}")

    # ---------- 知识库检索 ----------
    print("\n[7] 知识库（AI 检索的数据来源）")
    r = client.get("/api/v1/knowledge", headers=h_ou)
    check("全局知识库可访问", r.status_code == 200, f"got {r.status_code}")
    all_k = r.json()["data"]
    check("知识库含已沉淀条目", len(all_k) >= 2, f"got {len(all_k)}")
    if all_k:
        k = all_k[0]
        check("知识条目含标题", bool(k["title"]), str(k))
        check("知识条目含阶段标签", bool(k.get("stage_label")), str(k.keys()))
        check("知识条目含来源项目名", bool(k.get("project_name")), str(k.keys()))

    r = client.get("/api/v1/knowledge", headers=h_ou, params={"keyword": "地铁"})
    check("按关键词检索可访问", r.status_code == 200, f"got {r.status_code}")
    kw = r.json()["data"]
    check("关键词检索命中了地铁相关条目", len(kw) >= 1, f"got {len(kw)}")
    if kw:
        check("命中条目确实包含关键词",
              "地铁" in (kw[0]["title"] + (kw[0]["knowledge_summary"] or "")),
              str(kw[0]["title"]))

    r = client.get("/api/v1/knowledge", headers=h_ou, params={"keyword": "不存在的关键词xyz"})
    check("无命中时返回空列表", r.json()["data"] == [], str(r.json()["data"])[:80])

    r = client.get(f"/api/v1/projects/{pid}/knowledge", headers=h_ou)
    check("本项目知识条目可访问", r.status_code == 200, f"got {r.status_code}")

    # ---------- 重新打开 ----------
    print("\n[8] 重新打开已闭环问题（例外路径）")
    r = client.post(
        f"/api/v1/projects/{pid}/issues/{iid}/reopen",
        headers=h_ou,
        json={"reason": ""},
    )
    check("重新打开不填原因 → 被拒绝", r.status_code == 422 or r.status_code == 400,
          f"got {r.status_code}")

    r = client.post(
        f"/api/v1/projects/{pid}/issues/{iid}/reopen",
        headers=h_ou,
        json={"reason": "现场反馈抗浮锚杆施工困难，需重新评估方案"},
    )
    check("填了原因后重新打开成功", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        issue = r.json()["data"]
        check("状态回到处理中", issue["status"] == "IN_PROGRESS", issue.get("status"))
        check("闭环时间已清空", issue["closed_at"] is None, str(issue.get("closed_at")))
        check("追加了重新打开的记录",
              any("重新打开" in a["content"] for a in issue["actions"]),
              str([a["content"][:20] for a in issue["actions"]]))

    # 未闭环的问题不能重新打开
    r = client.post(
        f"/api/v1/projects/{pid}/issues/{iid}/reopen",
        headers=h_ou,
        json={"reason": "试试看能不能重复打开"},
    )
    check("未闭环问题重新打开 → 被拒绝", r.status_code == 400, f"got {r.status_code}")

    # ---------- 筛选 ----------
    print("\n[9] 筛选")
    r = client.get(f"/api/v1/projects/{pid}/issues", headers=h_ou, params={"only_unclosed": True})
    check("按未闭环筛选可访问", r.status_code == 200, f"got {r.status_code}")
    unc = r.json()["data"]
    check("筛选结果全部未闭环",
          all(x["status"] != "CLOSED" for x in unc), str([x["status"] for x in unc]))

    r = client.get(f"/api/v1/projects/{pid}/issues", headers=h_ou, params={"severity": "HIGH"})
    check("按严重度筛选可访问", r.status_code == 200, f"got {r.status_code}")
    check("筛选结果全部高危",
          all(x["severity"] == "HIGH" for x in r.json()["data"]),
          str([x["severity"] for x in r.json()["data"]]))

    r = client.get(f"/api/v1/projects/{pid}/issues", headers=h_ou, params={"status": "CLOSED"})
    check("按状态筛选可访问", r.status_code == 200, f"got {r.status_code}")

    # ---------- 权限边界 ----------
    print("\n[10] 权限边界")

    # 问题处理的参与者跨角色：勘察、监理、业主都应能提出问题。
    # 这是刻意设计 —— 如果要求 EDIT 权限，审核人就永远签不了自己的验证意见，
    # 而"验证"恰恰应该由非提出人来做才有意义。
    h_li = login(client, "ligong")  # 勘察单位（本项目参与人，阶段不含 DESIGN）
    r = client.post(
        f"/api/v1/projects/{pid}/issues",
        headers=h_li,
        json={
            "stage_code": "DESIGN",
            "title": "勘察单位提出：③层取样复验结果已出",
            "description": "补充的 3 组原状土样复验完成，③层 fak 建议由 280kPa 调整为 310kPa。",
        },
    )
    check("项目参与人（勘察）可以提出问题", r.status_code == 200,
          f"got {r.status_code} {r.text[:200]}")

    # 但**非本项目参与人**必须被拦住。
    # 注意：不能借"别的项目"来测 —— 演示账号可能同时参与多个项目
    # （王五既是杭州监理也是苏州监理，这是正常的）。
    # 所以直接造一个**不属于任何项目**的用户，测起来才稳。
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models.org import AppUser

    db = SessionLocal()
    try:
        outsider = (
            db.execute(select(AppUser).where(AppUser.username == "probe_outsider"))
            .scalar_one_or_none()
        )
        if outsider is None:
            import uuid as _uuid

            outsider = AppUser(
                id=_uuid.uuid4().hex,
                username="probe_outsider",
                name="探针（无项目）",
                password_hash=hash_password("Tjad@2026"),
                is_active=True,
                is_superuser=False,
            )
            db.add(outsider)
            db.commit()
    finally:
        db.close()

    h_out = login(client, "probe_outsider")
    r = client.post(
        f"/api/v1/projects/{pid}/issues",
        headers=h_out,
        json={
            "stage_code": "DESIGN",
            "title": "越权测试：非参与人给项目提问题",
            "description": "测试用",
        },
    )
    check("非项目参与人提问题 → 被拒绝", r.status_code == 403,
          f"got {r.status_code} {r.text[:200]}")

    r = client.get(f"/api/v1/projects/{pid}/issues", headers=h_out)
    check("非项目参与人查看问题列表 → 被拒绝", r.status_code == 403,
          f"got {r.status_code}")

    # ---------- 汇总 ----------
    print("\n" + "=" * 56)
    print(f"通过 {passed} 项，失败 {failed} 项")
    if failed == 0:
        print()
        print("提示：测试会在演示项目里创建 IS-* 问题单。")
        print("      需要干净演示数据时执行：")
        print("        .venv\\Scripts\\python.exe -m app.seed.seed_all --reset")
    print("=" * 56)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
