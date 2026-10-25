"""设计成果与交付完整性 —— 专项测试。

**这是设计院内部试用最实际的落点。**

验证六道关卡逐项拦截、以及逐个修好后能放行：

  1 INPUTS_LOCKED        设计输入已锁定
  2 PARAM_SOURCE_VALID   参数来源有效（无 STALE）
  3 DELIVERABLES_COMPLETE 成果齐备
  4 VERSIONS_PUBLISHED   版本均为已发布
  5 ISSUES_CLOSED        问题已闭环
  6 CHANGES_CLOSED       变更已闭环

重点不在于"最终能通过"，而在于**每一关都能独立拦住交付，
并且给出人话的原因和可操作的建议** —— 只说"检查不通过"，
用户根本不知道该怎么办。

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/test_deliverables.py
"""
from __future__ import annotations

import io
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


# 两级签认按**单位**派任务，所以这里按承办单位选人。
# 设计阶段：CONFIRM 派给设计单位；REVIEW 派给监理单位 + 政府审查单位。
UNIT_ACTOR_USERS = {
    "DESIGNER": "ouyuxin",
    "SUPERVISOR": "wangwu",
    "GOVERNMENT": "gongwu",
    "OWNER": "chenkaili",
    "SURVEYOR": "ligong",
    "DESIGN_TEST_PILE": "zhaosi",
    "GENERAL_CONTRACTOR": "sunqi",
    "SUBCONTRACTOR": "zhouba",
    "ACCEPT_TEST_PILE": "wujiu",
    "INSPECTOR": "zhengshi",
    "ADMIN": "admin",
}

#: 各阶段主办单位的代表人 —— **发布/作废必须由主办单位执行**（权限矩阵决定）
PRIMARY_UNIT_ACTOR = {
    "PRE_SURVEY": "chenkaili",        # 建设单位
    "INVESTIGATION": "ligong",        # 勘察单位
    "DESIGN_TEST_PILE": "zhaosi",     # 设计试桩单位
    "DESIGN": "ouyuxin",              # 设计单位
    "CONSTRUCTION": "sunqi",          # 总包单位
    "ACCEPT_TEST_PILE": "wujiu",      # 验收试桩单位
    "MONITORING": "zhengshi",         # 检测监测单位
}


def primary_actor_of(stage_code: str | None) -> str:
    """取某阶段主办单位的代表人。

    为什么需要：发布与作废是**主办单位**的动作，
    非主办单位（哪怕能看到文件）都会被 403 拦下。
    """
    return PRIMARY_UNIT_ACTOR.get(stage_code or "", "ouyuxin")


def approve_until_finished(client: TestClient, version_id: str, rounds: int = 6) -> str:
    """按节点指派依次审批，直到流程结束。

    若遇到「校核/审核/批准必须由不同人员完成」的拦截（演示项目里
    专职校核人/审核人可能覆盖不到全部节点），改为带 allow_self_check
    重试 —— 这条路径本身也是产品支持的（自校需显式开关并留痕）。
    """
    for _ in range(rounds):
        r = client.get(f"/api/v1/tasks/versions/{version_id}/trace", headers=login(client, "ouyuxin"))
        tr = r.json().get("data")
        if tr is None:
            return "NO_WORKFLOW"
        if tr["status"] == "FINISHED":
            return "FINISHED"
        task = next((t for t in tr["tasks"] if t["action"] is None), None)
        if task is None:
            return tr["status"]
        uname = UNIT_ACTOR_USERS.get(task.get("assignee_role"), "ouyuxin")
        r2 = client.post(
            f"/api/v1/versions/{version_id}/decide",
            headers=login(client, uname),
            json={"action": "APPROVE", "comment": f"{uname} 通过"},
        )
        if r2.status_code == 200:
            continue
        msg = r2.json().get("message", "")
        # 落到同一个人身上的相邻节点 → 显式走自校
        if "不同人员" in msg or "指派给其他成员" in msg:
            r3 = client.post(
                f"/api/v1/versions/{version_id}/decide",
                headers=login(client, "chenkaili"),
                json={"action": "APPROVE", "comment": "自校通过（人员不足）",
                      "allow_self_check": True},
            )
            if r3.status_code != 200:
                return f"ERROR:{r3.json().get('message')}"
            continue
        return f"ERROR:{msg}"
    return "MAX_ROUNDS"


def gate_of(result: dict, code: str) -> dict | None:
    return next((g for g in result["gates"] if g["code"] == code), None)


def main() -> int:
    client = TestClient(app)
    h_ou = login(client, "ouyuxin")
    h_chen = login(client, "chenkaili")

    # ---------- 准备 ----------
    print("\n[0] 准备：项目")
    r = client.get("/api/v1/projects", headers=h_ou)
    hz = next((p for p in r.json()["data"] if "杭州" in p["name"]), None)
    check("找到杭州项目", hz is not None)
    if not hz:
        return 1
    pid = hz["id"]

    # ---------- 成果清单 ----------
    print("\n[1] 设计成果清单")
    r = client.get(f"/api/v1/projects/{pid}/deliverables", headers=h_ou)
    check("成果清单可访问", r.status_code == 200, f"got {r.status_code}")
    dels = r.json()["data"]
    check("返回标准交付清单", len(dels) >= 5, f"got {len(dels)}")

    required = [d for d in dels if d["required"]]
    check("标准清单含 5 项必交成果", len(required) == 5, f"got {len(required)}")

    names = {d["type_name"] for d in dels}
    check("清单含桩基设计总说明", "桩基设计总说明" in names, str(names))
    check("清单含单桩承载力计算书", "单桩承载力计算书" in names, str(names))
    check("清单含桩基平面布置图", "桩基平面布置图" in names, str(names))
    check("清单含承台配筋图", "承台配筋图" in names, str(names))
    check("清单含桩基施工图", "桩基施工图" in names, str(names))

    # 已有文件的成果项应标注版本状态
    layout = next((d for d in dels if d["type_code"] == "LAYOUT_DWG"), None)
    check("找到桩基平面布置图", layout is not None)
    if layout:
        check("已存在的成果标注 exists", layout["exists"] is True, str(layout))
        check("已发布的成果标注当前有效版本",
              bool(layout.get("current_version_no")), str(layout.get("current_version_no")))

    # 缺失的成果应被标记
    missing = [d for d in dels if not d["exists"]]
    check("识别出缺失的成果项", len(missing) > 0, f"got {len(missing)}")
    if missing:
        check("缺失项给出 blocker 说明",
              any(d["blockers"] for d in missing), str(missing[0].get("blockers")))

    # ---------- 初次交付检查：应当不通过 ----------
    print("\n[2] 交付完整性检查（初始状态应拦截）")
    r = client.get(f"/api/v1/projects/{pid}/deliverables/check", headers=h_ou)
    check("检查接口可访问", r.status_code == 200, f"got {r.status_code}")
    res = r.json()["data"]
    check("初始状态不允许交付", res["can_deliver"] is False, str(res["can_deliver"]))
    check("返回六道关卡", len(res["gates"]) == 6, f"got {len(res['gates'])}")
    check("统计未通过关卡数", res["failed_gate_count"] > 0, str(res["failed_gate_count"]))
    check("统计待处理项数", res["blocker_count"] > 0, str(res["blocker_count"]))
    check("给出汇总说明", bool(res["summary"]), str(res.get("summary")))

    codes = {g["code"] for g in res["gates"]}
    expected_codes = {
        "INPUTS_LOCKED",
        "PARAM_SOURCE_VALID",
        "DELIVERABLES_COMPLETE",
        "VERSIONS_PUBLISHED",
        "ISSUES_CLOSED",
        "CHANGES_CLOSED",
    }
    check("六道关卡编码齐全", codes == expected_codes, str(codes))

    # 每一关都要有 detail 与 suggestion
    no_sugg = [g["code"] for g in res["gates"] if not g.get("suggestion")]
    check("每道关卡都给出可操作建议", not no_sugg, str(no_sugg))
    no_detail = [g["code"] for g in res["gates"] if not g.get("detail")]
    check("每道关卡都说明检查了什么", not no_detail, str(no_detail))

    # 关卡 1 应因未锁定而失败
    g1 = gate_of(res, "INPUTS_LOCKED")
    check("关卡1（设计输入已锁定）未通过", g1 is not None and g1["passed"] is False,
          str(g1))
    if g1:
        check("关卡1 指出未锁定的问题",
              any("锁定" in b for b in g1["blockers"]), str(g1["blockers"]))
        check("关卡1 给出锁定建议",
              "锁定" in (g1["suggestion"] or ""), str(g1.get("suggestion")))

    # 关卡 3 应因缺成果而失败
    g3 = gate_of(res, "DELIVERABLES_COMPLETE")
    check("关卡3（成果齐备）未通过", g3 is not None and g3["passed"] is False, str(g3))
    if g3:
        check("关卡3 列出了缺失的成果名称",
              any("缺少" in b for b in g3["blockers"]), str(g3["blockers"]))

    # 关卡 5 应因问题未闭环而失败
    g5 = gate_of(res, "ISSUES_CLOSED")
    check("关卡5（问题已闭环）未通过", g5 is not None and g5["passed"] is False, str(g5))
    if g5:
        check("关卡5 列出了未闭环问题",
              len(g5["blockers"]) > 0, str(g5["blockers"]))

    # 关卡 6 应因变更未闭环而失败
    g6 = gate_of(res, "CHANGES_CLOSED")
    check("关卡6（变更已闭环）未通过", g6 is not None and g6["passed"] is False, str(g6))

    # 关卡 2（参数来源有效）此刻应通过 —— 种子里没有 STALE 参数
    g2 = gate_of(res, "PARAM_SOURCE_VALID")
    check("关卡2（参数来源有效）初始通过", g2 is not None and g2["passed"] is True, str(g2))

    # ---------- 交付清单：只收录已发布 ----------
    print("\n[3] 交付清单只收录已发布版本")
    r = client.get(f"/api/v1/projects/{pid}/deliverables/manifest", headers=h_ou)
    check("交付清单可访问", r.status_code == 200, f"got {r.status_code}")
    man = r.json()["data"]
    check("清单有说明文字", bool(man["note"]), str(man.get("note")))
    check("说明强调只收录已发布版本",
          "已发布" in (man["note"] or ""), str(man.get("note")))
    for it in man["items"]:
        check(f"清单项「{it['type_name']}」有版本号", bool(it.get("version_no")), str(it))

    # ---------- 关卡 1：锁定设计输入 ----------
    print("\n[4] 修复关卡1：锁定设计输入")
    r = client.get(f"/api/v1/projects/{pid}/design-inputs", headers=h_ou)
    for p in r.json()["data"]:
        if p["verify_status"] != "VERIFIED":
            client.post(
                f"/api/v1/projects/{pid}/design-inputs/{p['id']}/verify",
                headers=h_ou,
                json={"action": "verify", "note": "交付前核验"},
            )
    r = client.post(f"/api/v1/projects/{pid}/design-inputs/lock", headers=h_ou, json={})
    check("锁定设计输入成功", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")

    r = client.get(f"/api/v1/projects/{pid}/deliverables/check", headers=h_ou)
    res2 = r.json()["data"]
    g1b = gate_of(res2, "INPUTS_LOCKED")
    check("锁定后关卡1 通过", g1b is not None and g1b["passed"] is True, str(g1b))
    check("关卡1 通过后待处理项减少",
          res2["blocker_count"] < res["blocker_count"],
          f"{res2['blocker_count']} vs {res['blocker_count']}")

    # ---------- 关卡 3/4：补齐成果并发布 ----------
    print("\n[5] 修复关卡3/4：补齐五项成果并发布")
    # 先看当前缺哪几项
    r = client.get(f"/api/v1/projects/{pid}/deliverables", headers=h_ou)
    dels = r.json()["data"]

    # 字典里取成果类型 id
    r = client.get("/api/v1/dict/items", headers=h_ou, params={"category": "DOC_TYPE"})
    type_map = {i["name"]: i["id"] for i in r.json()["data"]}

    # 成果项 → 文档类型名 的映射
    NAME_TO_DOCTYPE = {
        "DESIGN_SPEC": "设计说明",
        "CALC_BOOK": "计算书",
        "LAYOUT_DWG": "布置图",
        "REBAR_DWG": "配筋图",
        "CONSTR_DWG": "施工图",
    }

    created = 0
    for d in dels:
        if d["type_code"] not in NAME_TO_DOCTYPE:
            continue
        doc_type_name = NAME_TO_DOCTYPE[d["type_code"]]
        cat_id = type_map.get(doc_type_name)

        if not d["exists"]:
            # 新建文件
            r = client.post(
                "/api/v1/documents",
                headers=h_ou,
                json={
                    "project_id": pid,
                    "stage_code": "DESIGN",
                    "title": d["type_name"],
                    "doc_no": f"JG-TEST-{d['type_code']}",
                    "category_id": cat_id,
                    "discipline": "结构",
                    "secret_level": "INTERNAL",
                },
            )
            if r.status_code != 200:
                continue
            doc_id = r.json()["data"]["id"]
            created += 1
            # 首个版本：上传 → 提交 → 审批 → 发布
            content = f"DELIVERABLE-{d['type_code']}-CONTENT".encode()
            r = client.post(
                f"/api/v1/documents/{doc_id}/versions",
                headers=h_ou,
                files={"file": (f"{d['type_code']}.pdf", io.BytesIO(content), "application/pdf")},
                data={"change_summary": "交付用正式版本"},
            )
            if r.status_code != 200:
                continue
            vid = r.json()["data"]["id"]
            client.post(f"/api/v1/versions/{vid}/submit", headers=h_ou)
            approve_until_finished(client, vid)
        else:
            doc_id = d["document_id"]

        # 发布/作废必须由**该阶段的主办单位**执行（权限矩阵决定）。
        # 本接口按阶段查询，交付清单默认就是设计阶段，所以直接写 DESIGN。
        stage_of_doc = "DESIGN"

        # 把该文档推进到"有已发布版本且无未发布新版本"
        for _round in range(3):
            rv = client.get(f"/api/v1/documents/{doc_id}/versions", headers=h_ou)
            versions = rv.json()["data"]
            if not versions:
                break
            published = [v for v in versions if v["state"] == "PUBLISHED"]
            unpublished = [v for v in versions if v["state"] != "PUBLISHED"]

            # 审批中的先走完流程
            inflight = [v for v in unpublished if v["state"] in ("CHECKING", "REVIEWING")]
            for v in inflight:
                approve_until_finished(client, v["id"])

            # 草稿/修订中的提交审批后走完流程
            drafts = [v for v in unpublished if v["state"] in ("DRAFT", "REVISING")]
            for v in drafts:
                client.post(f"/api/v1/versions/{v['id']}/submit", headers=h_ou)
                approve_until_finished(client, v["id"])

            # 已批准的发布掉（若已有一个已发布版本，多余的作废）
            rv = client.get(f"/api/v1/documents/{doc_id}/versions", headers=h_ou)
            versions = rv.json()["data"]
            approved = [v for v in versions if v["state"] == "APPROVED"]
            has_published = any(v["state"] == "PUBLISHED" for v in versions)
            for v in approved:
                if has_published:
                    client.post(
                        f"/api/v1/versions/{v['id']}/void",
                        headers=login(client, primary_actor_of(stage_of_doc)),
                        json={"reason": "交付前清理：已有有效版本，本版作废"},
                    )
                else:
                    r = client.post(
                        f"/api/v1/versions/{v['id']}/publish",
                        headers=login(client, primary_actor_of(stage_of_doc)),
                        json={},
                    )
                    if r.status_code == 200:
                        has_published = True

            # 检查是否已达成"有已发布、无未发布"
            rv = client.get(f"/api/v1/documents/{doc_id}/versions", headers=h_ou)
            versions = rv.json()["data"]
            if any(v["state"] == "PUBLISHED" for v in versions) and all(
                v["state"] == "PUBLISHED" for v in versions
            ):
                break

    # 重新取一次检查结果（避免用旧快照断言）
    r = client.get(f"/api/v1/projects/{pid}/deliverables/check", headers=h_ou)
    res_after = r.json()["data"]
    g3b = gate_of(res_after, "DELIVERABLES_COMPLETE")
    g4b = gate_of(res_after, "VERSIONS_PUBLISHED")
    print(f"    (新建成果 {created} 项；关卡3 passed={g3b['passed']} 关卡4 passed={g4b['passed']})")
    if not g3b["passed"]:
        print(f"      关卡3 待办: {g3b['blockers']}")
    if not g4b["passed"]:
        print(f"      关卡4 待办: {g4b['blockers']}")

    check("补齐后关卡3 通过", g3b["passed"] is True, str(g3b["blockers"]))
    check("补齐后关卡4 通过", g4b["passed"] is True, str(g4b["blockers"]))

    # ---------- 关卡 5：闭环全部问题 ----------
    print("\n[6] 修复关卡5：闭环全部问题")
    r = client.get(f"/api/v1/projects/{pid}/issues", headers=h_ou, params={"only_unclosed": True})
    open_issues = r.json()["data"]
    print(f"    (待闭环问题 {len(open_issues)} 项)")

    for iss in open_issues:
        iid = iss["id"]
        detail = client.get(f"/api/v1/projects/{pid}/issues/{iid}", headers=h_ou).json()["data"]
        done = {a["action_type"] for a in detail["actions"]}
        # 按链路**顺序**补齐缺失环节。
        # 注意顺序必须是 DESCRIBE→QUERY→ANALYZE→SUGGEST→EXECUTE→VERIFY→CLOSE，
        # 否则会因为"链路不可跳步"被后端拒绝（踩过这个坑）。
        chain = [
            ("QUERY", "检索相关规范与同类项目做法"),
            ("ANALYZE", "经复核，确认为取样扰动导致指标偏低，偏差约 14%"),
            ("SUGGEST", "建议补充原状土复验，复验前按保守值设计。依据：JGJ 94-2008 §5.3.5"),
            ("EXECUTE", "已按建议修改设计文件并更新图纸，责任人欧雨欣"),
            ("VERIFY", "由审核人复核：已核对修改后文件，满足规范要求，验证通过"),
            ("CLOSE", "验证有效，问题闭环"),
        ]
        for atype, content in chain:
            if atype in done:
                continue
            r = client.post(
                f"/api/v1/projects/{pid}/issues/{iid}/actions",
                headers=h_ou,
                json={"action_type": atype, "content": content},
            )
            if r.status_code != 200:
                print(f"    (问题 {iss.get('issue_no')} 记录 {atype} 失败: "
                      f"{r.status_code} {r.json().get('message')})")
                break
            done.add(atype)

    r = client.get(f"/api/v1/projects/{pid}/deliverables/check", headers=h_ou)
    res4 = r.json()["data"]
    g5b = gate_of(res4, "ISSUES_CLOSED")
    check("闭环后关卡5 通过", g5b["passed"] is True, str(g5b["blockers"]))

    # ---------- 关卡 6：关闭全部变更 ----------
    print("\n[7] 修复关卡6：关闭全部变更")
    r = client.get(f"/api/v1/projects/{pid}/changes", headers=h_ou)
    open_changes = [
        c for c in r.json()["data"] if c["state"] not in ("CLOSED", "REJECTED")
    ]
    print(f"    (待关闭变更 {len(open_changes)} 项)")

    for c in open_changes:
        cid = c["id"]
        # 先处理全部影响明细
        detail = client.get(f"/api/v1/projects/{pid}/changes/{cid}", headers=h_ou).json()["data"]
        for imp in detail["impacts"]:
            if imp["handled"]:
                continue
            client.post(
                f"/api/v1/projects/{pid}/changes/{cid}/impacts/{imp['id']}/handle",
                headers=h_ou,
                json={"note": "已按变更后内容更新文件，并通知施工方与监理"},
            )

        state = detail["state"]
        # 待提交/影响分析中 → 提交审批
        if state in ("DRAFT", "IMPACT_ANALYZING"):
            client.post(f"/api/v1/projects/{pid}/changes/{cid}/submit", headers=h_ou)

        # 审批中 → 走完审批（按节点指派）
        for _ in range(5):
            d2 = client.get(f"/api/v1/projects/{pid}/changes/{cid}", headers=h_ou).json()["data"]
            if d2["state"] not in ("APPROVING",):
                break
            inst_id = d2["workflow_instance_id"]
            if not inst_id:
                break
            tr = client.get(f"/api/v1/tasks/instances/{inst_id}", headers=h_ou).json()["data"]
            if tr["status"] == "FINISHED":
                break
            task = next((t for t in tr["tasks"] if t["action"] is None), None)
            if task is None:
                break
            actor = {
                "SUPERVISOR": "wangwu",
                "GOVERNMENT": "gongwu",
                "DESIGNER": "ouyuxin",
                "IMPACT": "ouyuxin",
            }.get(task.get("assignee_role"), "ouyuxin")
            client.post(
                f"/api/v1/projects/{pid}/changes/{cid}/decide",
                headers=login(client, actor),
                json={"action": "APPROVE", "comment": f"{actor} 同意"},
            )

        # 最终关闭
        client.post(f"/api/v1/projects/{pid}/changes/{cid}/close", headers=h_ou)

    r = client.get(f"/api/v1/projects/{pid}/deliverables/check", headers=h_ou)
    res5 = r.json()["data"]
    g6b = gate_of(res5, "CHANGES_CLOSED")
    check("关闭后关卡6 通过", g6b["passed"] is True, str(g6b["blockers"]))

    # ---------- 最终：应当可以交付 ----------
    print("\n[8] 六关全过后应当允许交付")
    failed_gates = [g for g in res5["gates"] if not g["passed"]]
    if failed_gates:
        for g in failed_gates:
            print(f"    (未通过: 关卡{g['gate']} {g['name']} -> {g['blockers']})")

    check("全部关卡通过", res5["can_deliver"] is True,
          f"未通过关卡: {[g['code'] for g in failed_gates]}")
    check("未通过关卡数归零", res5["failed_gate_count"] == 0, str(res5["failed_gate_count"]))
    check("待处理项数归零", res5["blocker_count"] == 0, str(res5["blocker_count"]))
    check("汇总说明为可以交付",
          "可以交付" in (res5["summary"] or ""), str(res5.get("summary")))

    # ---------- 交付清单此时应包含全部五项 ----------
    print("\n[9] 交付清单完整性")
    r = client.get(f"/api/v1/projects/{pid}/deliverables/manifest", headers=h_ou)
    man = r.json()["data"]
    check("交付清单至少 5 项", man["item_count"] >= 5, f"got {man['item_count']}")
    check("清单项数与会话一致", man["item_count"] == len(man["items"]),
          f"{man['item_count']} vs {len(man['items'])}")

    # 清单里不应出现未发布版本
    r = client.get(f"/api/v1/projects/{pid}/documents", headers=h_ou)
    docs = {d["id"]: d for d in r.json()["data"]}
    bad = []
    for it in man["items"]:
        d = docs.get(it["document_id"])
        if d and d["current_version_id"]:
            vers = {v["id"]: v for v in d["versions"]}
            cur = vers.get(d["current_version_id"])
            if cur and cur["state"] != "PUBLISHED":
                bad.append(it["type_name"])
    check("清单内所有成果均为已发布版本", not bad, str(bad))

    # ---------- 权限边界：只读身份能做什么、不能做什么 ----------
    print("\n[10] 权限边界：只读身份（政府审查单位）")
    r = client.get(f"/api/v1/projects/{pid}/deliverables/manifest", headers=h_ou)
    check("项目参与人可生成交付清单", r.status_code == 200, f"got {r.status_code}")

    # 造一个**只读身份**的成员：政府审查单位在设计阶段是「审查」等级
    # （能看、能提意见，不能编辑、不能发布）。
    # 项目里没有"加参与人"的接口（权限配置靠种子数据），
    # 所以这里直接写库，用一个新用户避免动到演示账号。
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models.org import AppUser
    from app.models.project import ProjectMember

    db = SessionLocal()
    try:
        probe = (
            db.execute(select(AppUser).where(AppUser.username == "probe_viewer"))
            .scalar_one_or_none()
        )
        if probe is None:
            import uuid as _uuid

            probe = AppUser(
                id=_uuid.uuid4().hex,
                username="probe_viewer",
                name="探针（仅审查）",
                password_hash=hash_password("Tjad@2026"),
                is_active=True,
                is_superuser=False,
                must_change_password=False,
            )
            db.add(probe)
            db.flush()
        exists = db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == pid, ProjectMember.user_id == probe.id
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                ProjectMember(
                    project_id=pid,
                    user_id=probe.id,
                    role_code="GOVERNMENT",   # 设计阶段为「审查」：只读 + 提意见
                    data_scope="PROJECT",
                    stage_scope=None,          # None = 按矩阵推导
                )
            )
            db.commit()
    finally:
        db.close()

    h_probe = login(client, "probe_viewer")

    # 能看项目与成果清单（有 VIEW）
    r = client.get(f"/api/v1/projects/{pid}/deliverables", headers=h_probe)
    check("只读身份可看成果清单（有 VIEW）", r.status_code == 200, f"got {r.status_code}")

    # 但**不能发布**（不是主办单位）
    r = client.get(f"/api/v1/projects/{pid}/documents", headers=h_probe)
    if r.status_code == 200 and r.json()["data"]:
        doc_id = next(
            (d["id"] for d in r.json()["data"] if d.get("secret_level") == "INTERNAL"),
            r.json()["data"][0]["id"],
        )
        rv = client.get(f"/api/v1/documents/{doc_id}/versions", headers=h_probe)
        if rv.status_code == 200:
            published = next(
                (v for v in rv.json()["data"] if v["state"] == "PUBLISHED"), None
            )
            if published:
                r = client.post(
                    f"/api/v1/versions/{published['id']}/publish", headers=h_probe, json={}
                )
                check("只读身份不能发布文件（非主办单位）", r.status_code == 403,
                      f"got {r.status_code} {r.text[:160]}")
                if r.status_code == 403:
                    check("拒绝原因说明不是主办单位",
                          "主办单位" in r.json().get("message", ""),
                          r.json().get("message"))

    # ---------- STALE 会重新卡住关卡 2 ----------
    print("\n[11] 来源失效会重新卡住关卡2（回归防线）")
    # 让参数来源文件发布新版本 → 参数变 STALE
    r = client.get(f"/api/v1/projects/{pid}/design-inputs", headers=h_ou)
    src_doc_id = next(
        (p["source"]["document_id"] for p in r.json()["data"] if p.get("source")), None
    )
    check("参数来源指向某份文件", src_doc_id is not None, "所有参数都没有 source")

    if src_doc_id:
        r = client.post(
            f"/api/v1/documents/{src_doc_id}/revision",
            headers=h_ou,
            json={"reason": "补充复验结果，作为交付后更新"},
        )
        if r.status_code == 200:
            sv = r.json()["data"]
            client.post(f"/api/v1/versions/{sv['id']}/submit", headers=h_ou)
            approve_until_finished(client, sv["id"])
            client.post(
                f"/api/v1/versions/{sv['id']}/publish",
                headers=login(client, primary_actor_of("INVESTIGATION")),
                json={},
            )

            r = client.get(f"/api/v1/projects/{pid}/deliverables/check", headers=h_ou)
            res6 = r.json()["data"]
            g2c = gate_of(res6, "PARAM_SOURCE_VALID")
            check("来源更新后关卡2 重新拦住交付", g2c["passed"] is False, str(g2c))
            check("关卡2 指出参数来源已失效",
                  any("新版本" in b or "失效" in b for b in g2c["blockers"]),
                  str(g2c["blockers"]))
            check("来源更新后整体不再允许交付", res6["can_deliver"] is False,
                  str(res6["can_deliver"]))

    # ---------- 汇总 ----------
    print("\n" + "=" * 56)
    print(f"通过 {passed} 项，失败 {failed} 项")
    if failed == 0:
        print()
        print("提示：测试会在演示项目里创建成果文件、补齐问题与变更。")
        print("      需要干净演示数据时执行：")
        print("        .venv\\Scripts\\python.exe -m app.seed.seed_all --reset")
    print("=" * 56)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
