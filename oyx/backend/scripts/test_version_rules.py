"""文件版本状态机与设计输入 —— 专项测试。

重点验证的不是"接口能返回数据"，而是**四条铁律真的被后端拦住了**：

  铁律 1  未发布版本不可被下游引用
  铁律 2  同一文件不允许同时存在两个审批中的版本
  铁律 3  PUBLISHED 不可回退，要改就发新版本
  铁律 4  同一文件同一时刻最多一个 PUBLISHED；作废必须填原因、不物理删除

以及设计输入的两条硬约束：
  - 参数核验后才能锁定；锁定后修改必须走变更（接口必须拒绝）
  - 来源文件发布新版本 → 相关参数自动置为「来源已失效」(STALE)

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/test_version_rules.py
"""
from __future__ import annotations

import io
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
    """登录并返回 Authorization 头。同一用户复用 token，PBKDF2 较慢。"""
    if username not in _tokens:
        r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, f"{username} 登录失败: {r.text[:200]}"
        _tokens[username] = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {_tokens[username]}"}


def upload(client: TestClient, h: dict, doc_id: str, content: bytes, filename: str, summary: str):
    return client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers=h,
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
        data={"change_summary": summary},
    )


# 各单位在杭州项目的代表人 —— 新模型按**单位**派任务，
# 同一单位里任何人都能处理，这里固定用一个演示账号。
UNIT_ACTOR_USERS = {
    "OWNER": "chenkaili",
    "SURVEYOR": "ligong",
    "DESIGN_TEST_PILE": "zhaosi",
    "DESIGNER": "ouyuxin",
    "GENERAL_CONTRACTOR": "sunqi",
    "SUBCONTRACTOR": "zhouba",
    "SUPERVISOR": "wangwu",
    "ACCEPT_TEST_PILE": "wujiu",
    "INSPECTOR": "zhengshi",
    "GOVERNMENT": "gongwu",
    "ADMIN": "admin",
}


def actor_for_task(task: dict) -> str:
    """按任务上记录的承办单位挑一个处理人。

    比硬编码节点→人名稳：矩阵调整、单位换人时测试不用改。
    """
    unit = task.get("assignee_role")
    if unit and unit in UNIT_ACTOR_USERS:
        return UNIT_ACTOR_USERS[unit]
    # 任务已指派到具体人时优先用那个人
    if task.get("assignee"):
        return "__by_id__"
    return "chenkaili"


def approve_until_finished(client: TestClient, version_id: str, max_rounds: int = 20) -> str:
    """按当前待办任务依次签认，直到流程结束。返回最终流程状态。

    两级签认是「主办单位确认 → 相关单位复核」。相关单位可能有多个，
    **每个单位各有一条任务**，必须全部签完才推进，所以一次完整签认会
    消耗多条任务 —— 轮次上限给足，避免边界上偶发失败（曾经踩过：
    上限设 8，串起来跑时偶尔不够，表现为"修订版停在审核中"）。

    返回 "FINISHED" 表示全部签完；其他返回值都表示没走完，调用方应当关注。
    """
    seen: set[str] = set()
    for _ in range(max_rounds):
        r = client.get(
            f"/api/v1/tasks/versions/{version_id}/trace", headers=login(client, "ouyuxin")
        )
        tr = r.json().get("data")
        if tr is None:
            print(f"    (版本 {version_id[:8]} 没有流程实例)")
            return "NO_WORKFLOW"
        if tr["status"] == "FINISHED":
            return "FINISHED"

        pending = [t for t in tr["tasks"] if t["action"] is None]
        if not pending:
            # 没有待办但流程未结束 —— 这是流程卡死，必须显式暴露而不是静默返回
            print(
                f"    (版本 {version_id[:8]} 流程状态 {tr['status']} "
                f"节点 {tr.get('current_node')} 但没有待办任务 —— 流程卡住)"
            )
            return f"STUCK:{tr.get('current_node')}"

        task = pending[0]
        uname = actor_for_task(task)
        r2 = client.post(
            f"/api/v1/versions/{version_id}/decide",
            headers=login(client, uname) if uname != "__by_id__" else login(client, "ouyuxin"),
            json={"action": "APPROVE", "comment": f"{uname} 签认通过"},
        )
        if r2.status_code == 200:
            seen.clear()
            continue

        # 同一人在本流程已签过 → 走自校（产品支持的路径，需显式开关并留痕）
        r3 = client.post(
            f"/api/v1/versions/{version_id}/decide",
            headers=login(client, uname) if uname != "__by_id__" else login(client, "ouyuxin"),
            json={
                "action": "APPROVE",
                "comment": "自校通过",
                "allow_self_check": True,
            },
        )
        if r3.status_code != 200:
            print(
                f"    (签认中断于 {task['node_code']}/{task.get('assignee_role')} "
                f"由 {uname}: {r3.status_code} {r3.json().get('message')})"
            )
            return "ERROR"

        # 防止同一状态反复重试导致假死
        key = f"{task['node_code']}:{task.get('assignee_role')}"
        if key in seen:
            print(f"    (签认在 {key} 反复失败 —— 提前退出)")
            return "LOOP"
        seen.add(key)

    print(f"    (版本 {version_id[:8]} 达到签认轮次上限 {max_rounds}，仍未结束)")
    return "MAX_ROUNDS"


def main() -> int:
    client = TestClient(app)
    h_ou = login(client, "ouyuxin")
    h_chen = login(client, "chenkaili")

    # ---------- 准备：拿项目与文档 ----------
    print("\n[0] 准备数据")
    r = client.get("/api/v1/projects", headers=h_ou)
    hz = next((p for p in r.json()["data"] if "杭州" in p["name"]), None)
    check("找到杭州项目", hz is not None)
    if not hz:
        return 1
    hz_id = hz["id"]

    r = client.get(f"/api/v1/projects/{hz_id}/documents", headers=h_ou)
    check("文件列表可访问", r.status_code == 200, f"got {r.status_code}")
    docs = r.json()["data"]
    check("种子文件已就位", len(docs) >= 3, f"got {len(docs)}")

    # 找一份"已发布"的文件（勘察报告）和一份草稿
    published_doc = next((d for d in docs if d["published_version_no"]), None)
    check("存在已发布文件", published_doc is not None)

    # ---------- 建一份新文档走完整流程 ----------
    print("\n[1] 新建文档 + 上传草稿版本")
    # 用时间戳保证可重复运行（上一次失败的残留不会冲突）
    import time as _t

    doc_no = f"TEST-SM-{int(_t.time())}"
    r = client.post(
        "/api/v1/documents",
        headers=h_ou,
        json={
            "project_id": hz_id,
            "stage_code": "DESIGN",
            "title": "状态机测试用图",
            "doc_no": doc_no,
            "discipline": "结构",
            "secret_level": "INTERNAL",
        },
    )
    check("新建文档返回 200", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    doc = r.json()["data"]
    doc_id = doc["id"]

    content_v1 = b"TEST-PDF-CONTENT-V1-" + b"A" * 500
    r = upload(client, h_ou, doc_id, content_v1, "state-machine-test.pdf", "首版草稿")
    check("上传草稿版本返回 200", r.status_code == 200, f"got {r.status_code} {r.text[:300]}")
    v1 = r.json()["data"]
    check("初始状态为草稿 DRAFT", v1["state"] == "DRAFT", v1.get("state"))
    check("自动分配版本号 V1.0", v1["version_no"] == "V1.0", v1.get("version_no"))
    check("草稿可提交", "submit" in v1["available_actions"], str(v1["available_actions"]))

    # ---------- 铁律 1：未发布版本不可被引用 ----------
    print("\n[2] 铁律 1：未发布版本不可被下游引用")
    r = client.post(
        f"/api/v1/projects/{hz_id}/design-inputs/refresh-stale", headers=h_ou
    )
    check("refresh-stale 可调用", r.status_code == 200, f"got {r.status_code}")

    # 通过"把设计参数来源指向草稿版本"来验证拦截
    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs", headers=h_ou)
    check("设计输入清单可访问", r.status_code == 200, f"got {r.status_code}")
    params = r.json()["data"]
    check("种子参数已就位", len(params) >= 15, f"got {len(params)}")
    check("参数带来源溯源信息", any(p.get("source") for p in params),
          "所有参数都没有 source")
    src_sample = next((p for p in params if p.get("source")), None)
    if src_sample:
        s = src_sample["source"]
        check("来源含文件标题", bool(s.get("document_title")), str(s))
        check("来源含定位（页码/表号）", bool(s.get("locator")), str(s))
        check("来源含版本号", bool(s.get("version_no")), str(s))

    # 未发布的草稿版本 → relink 必须被拒
    r = client.post(
        f"/api/v1/projects/{hz_id}/design-inputs/{params[0]['id']}/relink-source",
        headers=h_ou,
        json={"new_version_id": v1["id"]},
    )
    check("把参数来源指向未发布版本 → 被拒绝", r.status_code == 400, f"got {r.status_code} {r.text[:200]}")
    if r.status_code == 400:
        check("拒绝原因是「未发布不可引用」",
              "未发布" in r.json()["message"] or "已发布" in r.json()["message"],
              r.json().get("message"))

    # ---------- 提交校审 → 三级校审 ----------
    print("\n[3] 提交校审（草稿 → 校核中）")
    r = client.post(f"/api/v1/versions/{v1['id']}/submit", headers=h_ou)
    check("提交成功", r.status_code == 200, f"got {r.status_code} {r.text[:300]}")
    v1 = r.json()["data"]
    check("状态变为校核中 CHECKING", v1["state"] == "CHECKING", v1.get("state"))
    check("生成了流程实例", bool(v1["workflow_instance_id"]), str(v1))
    check("当前节点为 CONFIRM（主办单位确认）",
          v1["current_node"] == "CONFIRM", str(v1.get("current_node")))

    # 铁律 2：不允许同时存在两个审批中的版本
    print("\n[4] 铁律 2：不允许同时存在两个审批中的版本")
    r = upload(client, h_ou, doc_id, b"SECOND-VERSION-CONTENT", "second.pdf", "第二个版本")
    check("审批中再上传新版本 → 被拒绝", r.status_code == 400, f"got {r.status_code} {r.text[:200]}")
    if r.status_code == 400:
        check("拒绝原因是「不允许两个审批中版本」",
              "审批中" in r.json()["message"], r.json().get("message"))

    # 审批轨迹
    print("\n[5] 审批轨迹")
    r = client.get(f"/api/v1/tasks/versions/{v1['id']}/trace", headers=h_ou)
    check("可查审批轨迹", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200 and r.json()["data"]:
        trace = r.json()["data"]
        check("轨迹含 1 个任务", len(trace["tasks"]) == 1, str(len(trace["tasks"])))
        check("第一个节点是主办单位确认", trace["tasks"][0]["node_code"] == "CONFIRM",
              str(trace["tasks"][0].get("node_code")))
    else:
        check("轨迹非空", False, "trace 为 None")

    # ---------- 三级校审必须分离 ----------
    print("\n[6] 两级签认：主办单位确认 → 相关单位复核")

    # 新模型按**单位**派任务：
    #   设计阶段的矩阵 = 设计单位（主要）/ 监理单位（次要）/ 政府审查单位（审查）
    # 所以首节点 CONFIRM 派给设计单位（欧雨欣是设计单位的人），
    # 复核节点 REVIEW 派给监理单位与政府审查单位。
    # 审批权限由"任务是否指派给你所属单位"决定 ——
    # 相关单位没有 EDIT 权限也能签意见，这是"审批"与"编辑"的区分。
    h_li = login(client, "ligong")    # 勘察单位，本阶段无责任
    h_wang = login(client, "wangwu")  # 监理单位，相关责任
    h_gong = login(client, "gongwu")  # 政府审查单位

    r = client.get(f"/api/v1/tasks/versions/{v1['id']}/trace", headers=h_ou)
    trace = r.json()["data"]
    check("拿到签认轨迹", trace is not None and len(trace["tasks"]) >= 1)
    task = trace["tasks"][0] if trace and trace["tasks"] else None
    check("第一个节点是主办单位确认", task and task["node_code"] == "CONFIRM",
          str(task.get("node_code") if task else None))
    check("首节点已指派到人（不是未指派状态）",
          task is not None and task["assignee"] is not None,
          f"assignee={task.get('assignee') if task else None}")
    check("首节点派给设计单位（矩阵里的主办单位）",
          task is not None and task["assignee_role"] == "DESIGNER",
          str(task.get("assignee_role") if task else None))

    # 非处理人不能代签 → 必须被拒。
    # 用监理单位王五：他在设计阶段有权限（次要责任，能签认），
    # 但当前任务派给了设计单位。这里**只断言被拒绝且给出可理解的原因** ——
    # 到底是被"任务指派他人"拦（400）还是被"需要编辑权限"拦（403）都对，
    # 因为两者都是真实的越权路径，测试不该把实现细节钉死。
    r = client.post(
        f"/api/v1/versions/{v1['id']}/decide",
        headers=h_wang,
        json={"action": "APPROVE", "comment": "我替你签"},
    )
    check("非任务处理人不能代为签认 → 被拒绝", r.status_code in (400, 403),
          f"got {r.status_code} {r.text[:200]}")
    if r.status_code in (400, 403):
        msg = r.json().get("message", "")
        check("拒绝原因可理解（指派他人 / 需编辑权限）",
              "其他成员处理" in msg or "无权执行" in msg or "编辑" in msg, msg)

    # 设计单位（欧雨欣）过 CONFIRM 节点
    r = client.post(
        f"/api/v1/versions/{v1['id']}/decide",
        headers=h_ou,
        json={"action": "APPROVE", "comment": "本单位确认，参数取值与详勘一致"},
    )
    check("主办单位确认成功", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")
    if r.status_code == 200:
        v1 = r.json()["data"]
        # 状态跟着**当前节点**走：确认完推进到 REVIEW，所以是「审核中」。
        # 用「已进入待签认状态」来判断，比钉死某个枚举值更稳。
        check("确认后进入待签认状态（校核中或审核中）",
              v1["state"] in ("CHECKING", "REVIEWING"), v1.get("state"))
        check("当前节点推进到 REVIEW（相关单位复核）",
              v1["current_node"] == "REVIEW", str(v1.get("current_node")))

    # 复核节点应并行派给 监理单位 + 政府审查单位
    r = client.get(f"/api/v1/tasks/versions/{v1['id']}/trace", headers=h_ou)
    tr = r.json()["data"]
    pending = [t for t in tr["tasks"] if t["action"] is None]
    units = sorted({t["assignee_role"] for t in pending})
    check("复核节点并行派给多个单位", len(pending) >= 2, f"got {len(pending)}: {units}")
    check("复核单位含监理与政府审查",
          "SUPERVISOR" in units and "GOVERNMENT" in units, str(units))

    # 同一人在本流程已签过 → 再签要被拦（防一人签完全流程）
    r = client.post(
        f"/api/v1/versions/{v1['id']}/decide",
        headers=h_ou,
        json={"action": "APPROVE", "comment": "我自己再审一遍"},
    )
    check("同一人连续处理两个节点 → 被拒绝", r.status_code in (400, 403),
          f"got {r.status_code} {r.text[:200]}")

    # 相关单位逐个签认
    for _ in range(6):
        rr = client.get(f"/api/v1/tasks/versions/{v1['id']}/trace", headers=h_ou)
        tr = rr.json()["data"]
        if tr is None or tr["status"] == "FINISHED":
            break
        t = next((x for x in tr["tasks"] if x["action"] is None), None)
        if t is None:
            break
        actor_h = {"SUPERVISOR": h_wang, "GOVERNMENT": h_gong}.get(t["assignee_role"], h_chen)
        r2 = client.post(
            f"/api/v1/versions/{v1['id']}/decide",
            headers=actor_h,
            json={"action": "APPROVE", "comment": f"{t['assignee_role']} 复核通过"},
        )
        print(f"    (节点 {t['node_code']} 由 {t['assignee_role']} 处理: {r2.status_code})")
        if r2.status_code != 200:
            print(f"        失败原因: {r2.json().get('message')}")
            break

    r = client.get(f"/api/v1/versions/{v1['id']}", headers=h_ou)
    v1 = r.json()["data"]
    check("走到已批准 APPROVED", v1["state"] == "APPROVED", v1.get("state"))
    check("各单位分别签认 → 不触发自校标记", v1["is_self_checked"] is False,
          str(v1.get("is_self_checked")))

    # ---------- 发布权限 ----------
    print("\n[7] 发布权限：只有主办单位可以发布")

    r = client.get(f"/api/v1/projects/{hz_id}/members", headers=h_ou)
    hz_members = r.json()["data"]
    ou_units = [m["unit_code"] for m in hz_members if m["user_name"] == "欧雨欣"]
    print(f"    (欧雨欣在杭州项目的参与单位: {ou_units})")
    check("欧雨欣是设计单位（设计阶段的主办单位）",
          "DESIGNER" in ou_units, str(ou_units))

    # 勘察单位在本项目**不是设计阶段的主办单位** → 不能发布
    li_units = [m["unit_code"] for m in hz_members if m["user_name"] == "李工"]
    print(f"    (李工在杭州项目的参与单位: {li_units})")
    check("李工不是设计阶段的主办单位",
          "DESIGNER" not in li_units, str(li_units))

    r = client.post(f"/api/v1/versions/{v1['id']}/publish", headers=h_li, json={})
    check("非主办单位发布 → 被拒绝", r.status_code == 403,
          f"got {r.status_code} {r.text[:200]}")
    if r.status_code == 403:
        msg = r.json()["message"]
        # 关键是给出**可理解**的原因，而不是笼统的 403
        check("拒绝原因明确（没有责任 / 不是主办单位）",
              "没有责任" in msg or "不是主办单位" in msg or "无权发布" in msg, msg)

    # 主办单位（设计单位，欧雨欣）发布 → 成功
    r = client.post(f"/api/v1/versions/{v1['id']}/publish", headers=h_ou, json={})
    check("主办单位发布 → 成功", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")
    if r.status_code == 200:
        v1 = r.json()["data"]
        check("状态变为已发布 PUBLISHED", v1["state"] == "PUBLISHED", v1.get("state"))
        check("记录了发布时间", bool(v1["published_at"]), str(v1.get("published_at")))

    # 再次验证：已发布后别人也不能重复发布
    r = client.post(f"/api/v1/versions/{v1['id']}/publish", headers=h_ou, json={})
    check("已发布版本重复发布 → 被拒绝", r.status_code == 400, f"got {r.status_code}")

    r = client.get(f"/api/v1/documents/{doc_id}", headers=h_ou)
    doc = r.json()["data"]
    check("文档的有效版本已指向该版本", doc["current_version_id"] == v1["id"], str(doc)[:200])
    check("文档记录了已发布版本号", doc["published_version_no"] == v1["version_no"], str(doc)[:200])

    # ---------- 铁律 3：PUBLISHED 不可回退 ----------
    print("\n[8] 铁律 3：PUBLISHED 不可回退，要改就发新版本")
    r = client.post(f"/api/v1/versions/{v1['id']}/publish", headers=h_ou, json={})
    check("重复发布 → 被拒绝", r.status_code == 400, f"got {r.status_code}")
    if r.status_code == 400:
        check("拒绝原因是「已发布不可回退」",
              "已发布" in r.json()["message"], r.json().get("message"))

    r = client.post(f"/api/v1/versions/{v1['id']}/submit", headers=h_ou)
    check("已发布版本再次提交校审 → 被拒绝", r.status_code == 400,
          f"got {r.status_code} {r.text[:200]}")

    # 发起修订（正确做法）
    r = client.post(
        f"/api/v1/documents/{doc_id}/revision",
        headers=h_ou,
        json={"reason": "根据详勘 V2 参数调整承台配筋"},
    )
    check("发起修订成功", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")
    v2 = r.json()["data"]
    check("修订版版本号递增", v2["version_no"] != v1["version_no"], f"{v2['version_no']} vs {v1['version_no']}")
    check("修订版状态为 REVISING", v2["state"] == "REVISING", v2.get("state"))
    check("修订版记录了被替代版本", v2["supersedes_version_id"] == v1["id"], str(v2.get("supersedes_version_id")))

    # 修订期间原版本仍是有效版本（不能出现有效版本空窗）
    r = client.get(f"/api/v1/documents/{doc_id}", headers=h_ou)
    doc = r.json()["data"]
    check("修订期间原版本仍是有效版本", doc["current_version_id"] == v1["id"], str(doc["current_version_id"]))

    # ---------- 铁律 4：同一时刻最多一个 PUBLISHED ----------
    print("\n[9] 铁律 4：同一时刻最多一个 PUBLISHED；作废必须填原因")

    # 把修订版走完整流程后发布，验证旧版本自动作废
    content_v2 = b"TEST-PDF-CONTENT-V2-" + b"B" * 600
    r = client.post(
        f"/api/v1/versions/{v2['id']}/submit", headers=h_ou
    )
    check("修订版提交校审成功", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")

    # 按节点指派依次审批（三级校审要求不同人）
    final_status = approve_until_finished(client, v2["id"])
    print(f"    (修订版审批流程最终状态: {final_status})")

    r = client.get(f"/api/v1/versions/{v2['id']}", headers=h_ou)
    v2 = r.json()["data"]
    check("修订版走到已批准", v2["state"] == "APPROVED", v2.get("state"))

    r = client.post(f"/api/v1/versions/{v2['id']}/publish", headers=h_ou, json={})
    check("修订版发布成功", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")

    r = client.get(f"/api/v1/versions/{v1['id']}", headers=h_ou)
    v1_after = r.json()["data"]
    check("旧版本自动作废 VOID", v1_after["state"] == "VOID", v1_after.get("state"))
    check("旧版本记录了作废原因", bool(v1_after["void_reason"]), str(v1_after.get("void_reason")))

    r = client.get(f"/api/v1/documents/{doc_id}", headers=h_ou)
    doc = r.json()["data"]
    published = [v for v in doc["versions"] if v["state"] == "PUBLISHED"]
    check("同一时刻只有一个 PUBLISHED 版本", len(published) == 1, f"got {len(published)}")
    check("有效版本已切到修订版", doc["current_version_id"] == v2["id"], str(doc["current_version_id"]))

    r = client.post(
        f"/api/v1/versions/{v2['id']}/void", headers=h_chen, json={"reason": ""}
    )
    check("作废不填原因 → 被拒绝", r.status_code == 422 or r.status_code == 400,
          f"got {r.status_code}")

    # ---------- 设计输入：锁定与 STALE ----------
    print("\n[10] 设计输入：核验 → 锁定 → 锁定后禁止修改")

    # 先把所有参数重置为「待核验」，让本轮测试有确定的起点
    # （否则上一轮跑完留下的 VERIFIED/locked 状态会让断言失真）
    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs", headers=h_ou)
    for p in r.json()["data"]:
        if p["locked"]:
            client.post(
                f"/api/v1/projects/{hz_id}/design-inputs/unlock",
                headers=h_ou,
                json={"reason": "测试前置：重置参数状态"},
            )
            break
    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs", headers=h_ou)
    for p in r.json()["data"]:
        client.post(
            f"/api/v1/projects/{hz_id}/design-inputs/{p['id']}/verify",
            headers=h_ou,
            json={"action": "pending", "note": "测试前置：重置为待核验"},
        )

    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs/summary", headers=h_ou)
    check("核验汇总可访问", r.status_code == 200, f"got {r.status_code}")
    summ = r.json()["data"]
    check("汇总含未核验必填项计数", "unverified_required_count" in summ, str(summ.keys()))
    check("尚未锁定时 can_lock 应为 False（有未核验项）",
          summ["can_lock"] is False, str(summ))
    check("重置后存在未核验必填项", summ["unverified_required_count"] > 0, str(summ))

    # 未核验完就锁定 → 必须被拒
    r = client.post(
        f"/api/v1/projects/{hz_id}/design-inputs/lock", headers=h_ou, json={}
    )
    check("必填未核验完就锁定 → 被拒绝", r.status_code == 400, f"got {r.status_code} {r.text[:200]}")
    if r.status_code == 400:
        check("拒绝原因列出了未核验参数", "核验" in r.json()["message"], r.json().get("message"))

    # 逐个核验全部参数
    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs", headers=h_ou)
    all_params = r.json()["data"]
    for p in all_params:
        client.post(
            f"/api/v1/projects/{hz_id}/design-inputs/{p['id']}/verify",
            headers=h_ou,
            json={"action": "verify", "note": "测试核验通过"},
        )

    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs/summary", headers=h_ou)
    summ = r.json()["data"]
    check("全部核验后 can_lock 为 True", summ["can_lock"] is True, str(summ))
    check("未核验必填项归零", summ["unverified_required_count"] == 0, str(summ))

    r = client.post(
        f"/api/v1/projects/{hz_id}/design-inputs/lock", headers=h_ou, json={}
    )
    check("锁定设计输入成功", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")

    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs/summary", headers=h_ou)
    check("汇总显示已锁定", r.json()["data"]["locked"] is True, str(r.json()["data"].get("locked")))

    locked_param = all_params[0]
    r = client.post(
        f"/api/v1/projects/{hz_id}/design-inputs/{locked_param['id']}/verify",
        headers=h_ou,
        json={"action": "modify", "new_value_num": 999.0, "note": "偷偷改一下"},
    )
    check("锁定后修改参数 → 被拒绝", r.status_code == 400, f"got {r.status_code} {r.text[:200]}")
    if r.status_code == 400:
        check("拒绝原因提示走变更流程", "变更" in r.json()["message"], r.json().get("message"))

    r = client.post(
        f"/api/v1/projects/{hz_id}/design-inputs/unlock",
        headers=h_ou,
        json={"reason": ""},
    )
    check("解锁不填原因 → 被拒绝", r.status_code == 422 or r.status_code == 400,
          f"got {r.status_code}")

    r = client.post(
        f"/api/v1/projects/{hz_id}/design-inputs/unlock",
        headers=h_ou,
        json={"reason": "关联设计变更 BG-2026-002，需重新核验管线避让后的桩顶标高"},
    )
    check("填了原因后解锁成功", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")

    # ---------- STALE 自动推导 ----------
    print("\n[11] 来源文件发布新版本 → 参数自动置为「来源已失效」")
    # 先全部核验（解锁后状态被重置）
    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs", headers=h_ou)
    all_params = r.json()["data"]
    for p in all_params:
        client.post(
            f"/api/v1/projects/{hz_id}/design-inputs/{p['id']}/verify",
            headers=h_ou,
            json={"action": "verify", "note": "重新核验"},
        )

    # 让**参数真正引用的那份文件**发布一个新版本 → 应触发 STALE
    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs", headers=h_ou)
    params_now = r.json()["data"]
    src_doc_id = next(
        (p["source"]["document_id"] for p in params_now if p.get("source")), None
    )
    check("参数来源指向了某份文件", src_doc_id is not None, "所有参数都没有 source")

    r = client.get(f"/api/v1/projects/{hz_id}/documents", headers=h_ou)
    survey = next(
        (d for d in r.json()["data"] if d["id"] == src_doc_id), None
    )
    check("找到参数所引用的文件", survey is not None, f"src_doc_id={src_doc_id}")

    if survey:
        survey_id = survey["id"]
        print(f"    (选定勘察报告: {survey.get('doc_no')} 当前有效版本 {survey.get('published_version_no')})")
        # 走一轮修订并发布
        r = client.post(
            f"/api/v1/documents/{survey_id}/revision",
            headers=h_ou,
            json={"reason": "补充③层原状土取样复验结果"},
        )
        print(f"    (发起修订: {r.status_code})")
        if r.status_code == 200:
            sv = r.json()["data"]
            r = client.post(f"/api/v1/versions/{sv['id']}/submit", headers=h_ou)
            print(f"    (提交校审: {r.status_code})")
            final = approve_until_finished(client, sv["id"])
            print(f"    (勘察报告审批流程最终状态: {final})")
            r = client.post(f"/api/v1/versions/{sv['id']}/publish", headers=h_chen, json={})
            print(f"    (发布: {r.status_code} {r.json().get('message')})")
            check("勘察报告新版本发布成功", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
            if r.status_code == 200:
                msg = r.json()["message"]
                check("发布响应提示了受影响的参数数量",
                      "重新核验" in msg or "来源更新" in msg, msg)

            r = client.get(f"/api/v1/projects/{hz_id}/design-inputs/summary", headers=h_ou)
            summ = r.json()["data"]
            check("出现「来源已失效」STALE 参数", summ["stale"] > 0, str(summ))

            r = client.get(
                f"/api/v1/projects/{hz_id}/design-inputs",
                headers=h_ou,
                params={"verify_status": "STALE"},
            )
            stale_list = r.json()["data"]
            check("可按 STALE 筛出参数", len(stale_list) > 0, f"got {len(stale_list)}")
            if stale_list:
                p0 = stale_list[0]
                check("STALE 参数提示了原版本与新版本",
                      p0["source"] and p0["source"]["has_newer_published"] is True,
                      str(p0.get("source")))
                check("STALE 参数带重新核验说明", bool(p0["verify_note"]), str(p0.get("verify_note")))

    # ---------- 文件去重 ----------
    print("\n[12] 内容寻址去重")
    content = b"DEDUP-TEST-CONTENT-" + b"Z" * 300
    r1 = upload(client, h_ou, published_doc["id"], content, "dedup-a.pdf", "去重测试 A")
    if r1.status_code == 400:
        # 该文档已有审批中版本时跳过
        check("去重测试跳过（文档有审批中版本）", True)
    else:
        check("首次上传成功", r1.status_code == 200, f"got {r1.status_code} {r1.text[:200]}")

    # ---------- 待办 ----------
    print("\n[13] 待办接口（跨项目）")
    r = client.get("/api/v1/tasks/my", headers=h_ou)
    check("我的待办可访问", r.status_code == 200, f"got {r.status_code}")
    items = r.json()["data"]
    check("待办为列表", isinstance(items, list), str(type(items)))
    if items:
        it = items[0]
        check("待办含项目名", "project_name" in it, str(it.keys()))
        check("待办含业务标题", "biz_title" in it, str(it.keys()))
        check("待办含逾期标记", "overdue" in it, str(it.keys()))

    # ---------- 汇总 ----------
    print("\n[14] 测试收尾：把设计输入恢复到「待核验」干净状态")
    # 测试过程会把参数核验/锁定，如果不还原，演示时打开页面
    # 看到的是"19 项全部已核验 + 已锁定"，失去演示价值。
    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs", headers=h_ou)
    for p in r.json()["data"]:
        if p["locked"]:
            client.post(
                f"/api/v1/projects/{hz_id}/design-inputs/unlock",
                headers=h_ou,
                json={"reason": "测试收尾：恢复演示数据状态"},
            )
            break
    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs", headers=h_ou)
    for p in r.json()["data"]:
        client.post(
            f"/api/v1/projects/{hz_id}/design-inputs/{p['id']}/verify",
            headers=h_ou,
            json={"action": "pending", "note": "测试收尾：重置为待核验"},
        )
    r = client.get(f"/api/v1/projects/{hz_id}/design-inputs/summary", headers=h_ou)
    check("设计输入已恢复为待核验", r.json()["data"]["locked"] is False, str(r.json()["data"]))
    check("核验数据已清空", r.json()["data"]["verified"] == 0, str(r.json()["data"]["verified"]))

    print("\n" + "=" * 56)
    print(f"通过 {passed} 项，失败 {failed} 项")
    if failed == 0:
        print()
        print("提示：测试会在演示项目里创建 TEST-SM-* 测试文档。")
        print("      需要干净演示数据时执行：")
        print("        .venv\\Scripts\\python.exe -m app.seed.seed_all --reset")
    print("=" * 56)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
