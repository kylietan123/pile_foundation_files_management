"""工作台 —— 专项测试。

跨项目交办事项是"一人多项目"场景下的刚需：
每天要知道"有什么卡在我这里"，而不是一个项目一个项目点。

测试重点：
  1 三类事项分类正确（等我签认 / 被退回 / 我经手在途）
  2 **跨项目聚合** —— 别的项目的待办也要出现
  3 被退回的版本能被识别出来
  4 逾期标记正确
  5 项目维度的交办事项按阶段聚合
  6 只返回我参与的项目的待办（权限）

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/test_workbench.py
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
    if username not in _tokens:
        r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, f"{username} 登录失败: {r.text[:200]}"
        _tokens[username] = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {_tokens[username]}"}


def upload_and_submit(client: TestClient, h: dict, project_id: str, title: str,
                      doc_no: str, stage: str = "DESIGN") -> str | None:
    """建文件 + 上传 + 提交，返回 version_id。"""
    r = client.post(
        "/api/v1/documents",
        headers=h,
        json={
            "project_id": project_id, "stage_code": stage, "title": title,
            "doc_no": doc_no, "discipline": "结构", "secret_level": "INTERNAL",
        },
    )
    if r.status_code != 200:
        return None
    doc_id = r.json()["data"]["id"]
    r = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers=h,
        files={"file": ("wb.pdf", io.BytesIO(b"workbench test"), "application/pdf")},
        data={"change_summary": "工作台测试"},
    )
    if r.status_code != 200:
        return None
    vid = r.json()["data"]["id"]
    r = client.post(f"/api/v1/versions/{vid}/submit", headers=h)
    return vid if r.status_code == 200 else None


def main() -> int:
    client = TestClient(app)

    # ---------- 准备 ----------
    print("\n[0] 准备：项目与账号")
    h_ou = login(client, "ouyuxin")
    projs = client.get("/api/v1/projects", headers=h_ou).json()["data"]
    hz = next((p for p in projs if "杭州" in p["name"]), None)
    sh = next((p for p in projs if "上海" in p["name"]), None)
    check("找到杭州项目", hz is not None)
    check("找到上海项目（用于跨项目测试）", sh is not None)
    if not hz:
        return 1

    # ---------- 工作台基本结构 ----------
    print("\n[1] 我的工作（跨项目）")
    r = client.get("/api/v1/workbench/my-work", headers=h_ou)
    check("工作台可访问", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    wb = r.json()["data"]
    for k in ("awaiting", "returned", "inflight", "awaiting_count", "returned_count"):
        check(f"返回字段 {k}", k in wb, str(wb.keys()))
    check("三类计数与列表长度一致",
          wb["awaiting_count"] == len(wb["awaiting"])
          and wb["returned_count"] == len(wb["returned"])
          and wb["inflight_count"] == len(wb["inflight"]),
          f"{wb['awaiting_count']}/{len(wb['awaiting'])}")

    # ---------- 造一个"等我签认" ----------
    print("\n[2] 等我签认：别人提交，卡在我这里")
    # 设计单位（欧雨欣）提交 → 设计阶段主办确认派给设计单位
    vid = upload_and_submit(client, h_ou, hz["id"], "工作台测试图-杭州", "TEST-WB-01")
    check("成功提交一份文件", vid is not None, str(vid))

    r = client.get("/api/v1/workbench/my-work", headers=h_ou)
    wb2 = r.json()["data"]
    mine = [a for a in wb2["awaiting"] if a.get("doc_no") == "TEST-WB-01"]
    check("自己的工作台里出现待签项", bool(mine), str([a.get("doc_no") for a in wb2["awaiting"]]))
    if mine:
        it = mine[0]
        check("事项类型为 AWAITING_ME", it["kind"] == "AWAITING_ME", it.get("kind"))
        check("带项目名", bool(it.get("project_name")), str(it.get("project_name")))
        check("带阶段码", it.get("stage_code") == "DESIGN", str(it.get("stage_code")))
        check("带节点名", bool(it.get("node_name")), str(it.get("node_name")))
        check("带我的承办单位", bool(it.get("my_unit_label")), str(it.get("my_unit_label")))
        check("带提交人姓名", bool(it.get("submitted_by")), str(it.get("submitted_by")))
        check("带版本状态", it.get("version_state") == "CHECKING", str(it.get("version_state")))
        check("带到期时间", it.get("due_at") is not None, str(it.get("due_at")))
        check("未逾期", it["overdue"] is False, str(it.get("overdue")))

    # 相关单位（监理）也应看到同一个待签（复核节点在确认之后，此时还没有）
    h_wang = login(client, "wangwu")
    r = client.get("/api/v1/workbench/my-work", headers=h_wang)
    wb_wang = r.json()["data"]
    wang_item = [a for a in wb_wang["awaiting"] if a.get("doc_no") == "TEST-WB-01"]
    check("监理此刻没有该待签（还没轮到复核）", not wang_item,
          str([a.get("doc_no") for a in wb_wang["awaiting"]]))

    # 设计单位确认后 → 复核任务派给监理 + 政府审查
    r = client.get(f"/api/v1/tasks/versions/{vid}/trace", headers=h_ou)
    tr = r.json()["data"]
    task = next((t for t in tr["tasks"] if t["action"] is None), None)
    if task:
        client.post(
            f"/api/v1/versions/{vid}/decide",
            headers=h_ou,
            json={"action": "APPROVE", "comment": "主办确认"},
        )
    r = client.get("/api/v1/workbench/my-work", headers=h_wang)
    wb_wang2 = r.json()["data"]
    wang_item2 = [a for a in wb_wang2["awaiting"] if a.get("doc_no") == "TEST-WB-01"]
    check("确认后监理看到复核待办", bool(wang_item2),
          str([a.get("doc_no") for a in wb_wang2["awaiting"]]))
    if wang_item2:
        check("监理的待办标出承办单位",
              bool(wang_item2[0].get("my_unit_label")), str(wang_item2[0].get("my_unit_label")))

    # ---------- 跨项目聚合 ----------
    print("\n[3] 跨项目聚合")
    # 在上海项目也造一份等欧雨欣签的（上海项目她是设计单位）
    if sh:
        vid_sh = upload_and_submit(client, h_ou, sh["id"], "工作台测试图-上海", "TEST-WB-02")
        check("上海项目也提交一份", vid_sh is not None)
        r = client.get("/api/v1/workbench/my-work", headers=h_ou)
        wb3 = r.json()["data"]
        proj_names = {a.get("project_name") for a in wb3["awaiting"]}
        check("待办跨项目聚合（含杭州与上海）",
              any("杭州" in (n or "") for n in proj_names)
              and any("上海" in (n or "") for n in proj_names),
              str(proj_names))

    # ---------- 被退回 ----------
    print("\n[4] 被退回：我提交的被打回")
    # 设计单位提交 → 让相关单位退回
    r = client.get(f"/api/v1/tasks/versions/{vid}/trace", headers=h_ou)
    tr = r.json()["data"]
    pending = [t for t in tr["tasks"] if t["action"] is None]
    if pending:
        # 用承办单位对应的人退回
        actor = {"SUPERVISOR": "wangwu", "GOVERNMENT": "gongwu", "DESIGNER": "ouyuxin"}.get(
            pending[0].get("assignee_role"), "ouyuxin"
        )
        r = client.post(
            f"/api/v1/versions/{vid}/decide",
            headers=login(client, actor),
            json={"action": "RETURN", "comment": "内容需补充③层参数依据"},
        )
        check("退回成功", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")

        r = client.get("/api/v1/workbench/my-work", headers=h_ou)
        wb4 = r.json()["data"]
        ret = [x for x in wb4["returned"] if x.get("doc_no") == "TEST-WB-01"]
        check("工作台出现被退回项", bool(ret), str([x.get("doc_no") for x in wb4["returned"]]))
        if ret:
            check("被退回项类型正确", ret[0]["kind"] == "RETURNED_TO_ME", ret[0].get("kind"))
            check("被退回项状态为草稿/修订中",
                  ret[0]["version_state"] in ("DRAFT", "REVISING"),
                  str(ret[0].get("version_state")))

        # **被退回的文件不能同时出现在"等我签认"里。**
        # 退回后流程会新建一轮并回到首节点，系统可能给提交人自己派一条
        # "主办单位确认"任务 —— 那等于让他自己签自己，
        # 而且文件还没重新提交，不该让别人看到。必须滤掉。
        still_awaiting = [
            x for x in wb4["awaiting"] if x.get("doc_no") == "TEST-WB-01"
        ]
        check("被退回的文件不出现在「等我签认」里",
              not still_awaiting,
              str([(x.get("doc_no"), x.get("version_state")) for x in still_awaiting]))

    # ---------- 项目维度的交办事项 ----------
    print("\n[5] 项目交办事项（按阶段聚合）")
    r = client.get(f"/api/v1/workbench/projects/{hz['id']}/work", headers=h_ou)
    check("项目交办事项可访问", r.status_code == 200, f"got {r.status_code}")
    pw = r.json()["data"]
    check("带 project_id", pw.get("project_id") == hz["id"], str(pw.get("project_id")))
    check("只含本项目的事项",
          all(x["project_id"] == hz["id"] for x in pw["awaiting"] + pw["returned"]),
          "存在其他项目的事项")
    check("按阶段聚合字段存在", "by_stage" in pw, str(pw.keys()))
    if pw["by_stage"]:
        b = pw["by_stage"][0]
        check("阶段聚合带中文名", bool(b.get("stage_label")), str(b))

    # ---------- 权限：别人的待办看不到 ----------
    print("\n[6] 权限边界")
    # 造一个不属于任何项目的用户
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models.org import AppUser
    from sqlalchemy import select as _select

    db = SessionLocal()
    try:
        outsider = db.execute(
            _select(AppUser).where(AppUser.username == "probe_outsider")
        ).scalar_one_or_none()
        if outsider is None:
            import uuid as _uuid

            db.add(
                AppUser(
                    id=_uuid.uuid4().hex,
                    username="probe_outsider",
                    name="探针（无项目）",
                    password_hash=hash_password(PASSWORD),
                    is_active=True,
                    is_superuser=False,
                )
            )
            db.commit()
    finally:
        db.close()

    h_out = login(client, "probe_outsider")
    r = client.get("/api/v1/workbench/my-work", headers=h_out)
    check("非参与人工作台为空", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        d = r.json()["data"]
        check("非参与人没有任何待办",
              d["awaiting_count"] == 0 and d["returned_count"] == 0,
              f"{d['awaiting_count']}/{d['returned_count']}")

    r = client.get(f"/api/v1/workbench/projects/{hz['id']}/work", headers=h_out)
    check("非参与人查项目交办 → 被拒绝", r.status_code == 403, f"got {r.status_code}")

    # ---------- 汇总 ----------
    print("\n" + "=" * 56)
    print(f"通过 {passed} 项，失败 {failed} 项")
    if failed == 0:
        print()
        print("提示：测试会创建 TEST-WB-* 文件。")
        print("      需要干净演示数据时执行：")
        print("        .venv\\Scripts\\python.exe -m app.seed.seed_all --reset")
    print("=" * 56)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
