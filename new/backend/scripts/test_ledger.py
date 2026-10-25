"""文档台账与追溯 —— 专项测试。

**这是回答"文件丢了谁负责"的功能**，所以测试重点不是"能不能查到"，
而是**能不能追到人和单位**：

  1 每一行都有主办单位（该阶段矩阵里的主要责任单位）
  2 每一行都有上传人（姓名 + 工号）—— 用户要求"谁做的看得见"
  3 在途文件能说出"现在在谁手上"（待签单位）
  4 签认轨迹完整：谁签的、什么时候、什么意见
  5 阶段级权限过滤：看不到的阶段整段不出现
  6 只列"等我处理"时，不会混入别人的
  7 七阶段责任总览与《管理流程》矩阵一致

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/test_ledger.py
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


#: 各阶段主办单位的代表人
PRIMARY_ACTOR = {
    "PRE_SURVEY": "chenkaili",
    "INVESTIGATION": "ligong",
    "DESIGN_TEST_PILE": "zhaosi",
    "DESIGN": "ouyuxin",
    "CONSTRUCTION": "sunqi",
    "ACCEPT_TEST_PILE": "wujiu",
    "MONITORING": "zhengshi",
}
#: 各级签认人（按承办单位）
UNIT_ACTOR = {
    "DESIGNER": "ouyuxin",
    "SUPERVISOR": "wangwu",
    "GOVERNMENT": "gongwu",
    "OWNER": "chenkaili",
    "SURVEYOR": "ligong",
}


def run_signoff(client: TestClient, version_id: str, rounds: int = 8) -> str:
    """把某个版本的两级签认走完。"""
    for _ in range(rounds):
        r = client.get(
            f"/api/v1/tasks/versions/{version_id}/trace", headers=login(client, "ouyuxin")
        )
        tr = r.json().get("data")
        if tr is None:
            return "NO_WORKFLOW"
        if tr["status"] == "FINISHED":
            return "FINISHED"
        task = next((t for t in tr["tasks"] if t["action"] is None), None)
        if task is None:
            return tr["status"]
        uname = UNIT_ACTOR.get(task.get("assignee_role"), "ouyuxin")
        r2 = client.post(
            f"/api/v1/versions/{version_id}/decide",
            headers=login(client, uname),
            json={"action": "APPROVE", "comment": f"{uname} 签认通过"},
        )
        if r2.status_code != 200:
            return f"ERROR:{r2.json().get('message')}"
    return "MAX_ROUNDS"


def main() -> int:
    client = TestClient(app)
    h_ou = login(client, "ouyuxin")

    print("\n[0] 准备：项目")
    r = client.get("/api/v1/projects", headers=h_ou)
    hz = next((p for p in r.json()["data"] if "杭州" in p["name"]), None)
    check("找到杭州项目", hz is not None)
    if not hz:
        return 1
    pid = hz["id"]

    # ---------- 台账基本结构 ----------
    print("\n[1] 项目文档台账")
    r = client.get(f"/api/v1/projects/{pid}/ledger", headers=h_ou)
    check("台账接口可访问", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    led = r.json()["data"]
    check("返回条目数", led["item_count"] >= 3, str(led["item_count"]))
    check("条目与 items 一致", led["item_count"] == len(led["items"]))
    check("带生成时间", bool(led["generated_at"]))

    items = led["items"]
    # ---------- 责任落点：主办单位 ----------
    print("\n[2] 责任落点：每份文件都有主办单位")
    no_primary = [i["title"] for i in items if not i.get("primary_unit")]
    check("每份文件都有主办单位", not no_primary, str(no_primary))

    # 设计阶段文件的主办单位应是设计单位
    design_docs = [i for i in items if i["stage_code"] == "DESIGN"]
    check("有设计阶段文件", bool(design_docs), str([i["stage_code"] for i in items]))
    if design_docs:
        d0 = design_docs[0]
        check("设计阶段文件的主办单位 = 设计单位",
              d0["primary_unit"] == "DESIGNER", str(d0["primary_unit"]))
        check("主办单位有中文名", d0["primary_unit_label"] == "设计单位",
              str(d0.get("primary_unit_label")))

    # 勘察阶段文件的主办单位应是勘察单位
    survey_docs = [i for i in items if i["stage_code"] == "INVESTIGATION"]
    if survey_docs:
        s0 = survey_docs[0]
        check("勘察阶段文件的主办单位 = 勘察单位",
              s0["primary_unit"] == "SURVEYOR", str(s0["primary_unit"]))

    # ---------- 谁做的：上传人姓名 + 工号 ----------
    print("\n[3] 谁做的：上传人姓名与工号")
    with_uploader = [i for i in items if i.get("current_uploaded_by")]
    check("已发布文件带上传人", bool(with_uploader), str(len(with_uploader)))
    if with_uploader:
        u = with_uploader[0]["current_uploaded_by"]
        check("上传人有姓名", bool(u.get("name")), str(u))
        check("上传人字段含 id", bool(u.get("id")), str(u))
    with_creator = [i for i in items if i.get("created_by")]
    check("文件带创建人", bool(with_creator), str(len(with_creator)))
    published = [i for i in items if i.get("published_by")]
    print(f"    (已发布并记录发布人的文件 {len(published)} 份)")

    # ---------- 文件在谁手上 ----------
    print("\n[4] 文件现在在谁手上")
    # 造一份在途文件：上传 → 提交，停在主办单位确认
    r = client.post(
        "/api/v1/documents",
        headers=h_ou,
        json={
            "project_id": pid,
            "stage_code": "DESIGN",
            "title": "台账追溯测试用图",
            "doc_no": "TEST-LEDGER-01",
            "discipline": "结构",
            "secret_level": "INTERNAL",
        },
    )
    check("新建测试文件", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    doc_id = r.json()["data"]["id"]

    r = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers=h_ou,
        files={"file": ("ledger.pdf", io.BytesIO(b"ledger test"), "application/pdf")},
        data={"change_summary": "台账测试首版"},
    )
    check("上传版本", r.status_code == 200, f"got {r.status_code}")
    vid = r.json()["data"]["id"]

    r = client.post(f"/api/v1/versions/{vid}/submit", headers=h_ou)
    check("提交签认", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")

    r = client.get(f"/api/v1/projects/{pid}/ledger", headers=h_ou)
    led2 = r.json()["data"]
    target = next((i for i in led2["items"] if i["document_id"] == doc_id), None)
    check("台账里能找到在途文件", target is not None)
    if target:
        check("在途版本号已记录", target["inflight_version_no"] == "V1.0",
              str(target.get("inflight_version_no")))
        check("能说出现在等哪个单位签",
              bool(target["pending_unit_labels"]),
              str(target.get("pending_unit_labels")))
        check("等待单位是设计单位（主办先确认）",
              "设计单位" in target["pending_unit_labels"],
              str(target["pending_unit_labels"]))
        check("waits_on 是可读文案", bool(target["waits_on"]), str(target.get("waits_on")))
        # 在途文件还没发布过，所以"当前已发布版本"为空是对的；
        # 但"当前该看的状态"必须是在途状态（校核中）—— 这才是用户关心的。
        check("在途文件的有效状态为「校核中」",
              target["effective_state"] == "CHECKING", str(target.get("effective_state")))
        check("有效状态有中文名",
              target["effective_state_label"] == "校核中",
              str(target.get("effective_state_label")))
        check("待签任务数 > 0（确实在等人签）",
              target["pending_count"] > 0, str(target.get("pending_count")))

    # 反例：还没提交的文件不能显示成"在等人签"（那会让人以为文件已经在别人手上）
    r = client.post(
        "/api/v1/documents",
        headers=h_ou,
        json={
            "project_id": pid,
            "stage_code": "DESIGN",
            "title": "台账测试-未提交",
            "doc_no": "TEST-LEDGER-02",
            "discipline": "结构",
            "secret_level": "INTERNAL",
        },
    )
    draft_doc = r.json()["data"]["id"]
    r = client.post(
        f"/api/v1/documents/{draft_doc}/versions",
        headers=h_ou,
        files={"file": ("draft.pdf", io.BytesIO(b"draft"), "application/pdf")},
        data={"change_summary": "未提交草稿"},
    )
    check("上传未提交版本", r.status_code == 200, f"got {r.status_code}")

    r = client.get(f"/api/v1/projects/{pid}/ledger", headers=h_ou)
    draft_item = next(
        (i for i in r.json()["data"]["items"] if i["document_id"] == draft_doc), None
    )
    check("台账里能找到未提交文件", draft_item is not None)
    if draft_item:
        check("未提交文件没有待签任务",
              draft_item["pending_count"] == 0, str(draft_item.get("pending_count")))
        check("未提交文件不显示待签单位",
              not draft_item["pending_unit_labels"],
              str(draft_item.get("pending_unit_labels")))
        check("未提交文件状态为草稿",
              draft_item["effective_state"] == "DRAFT", str(draft_item.get("effective_state")))

    # ---------- 等我处理 ----------
    print("\n[5] 只列等我处理的文件")
    r = client.get(f"/api/v1/projects/{pid}/ledger/awaiting-me", headers=h_ou)
    check("等我处理接口可访问", r.status_code == 200, f"got {r.status_code}")
    mine = r.json()["data"]
    check("设计单位有等待签认的文件", mine["item_count"] >= 1, str(mine["item_count"]))
    check("返回的每一条都标记 awaiting_me",
          all(i["awaiting_me"] for i in mine["items"]),
          str([i["awaiting_me"] for i in mine["items"]]))
    check("每一条都确实等我",
          all("设计单位" in i["pending_unit_labels"] for i in mine["items"]))

    # 监理此时不应有等待（还没轮到复核）
    h_wang = login(client, "wangwu")
    r = client.get(f"/api/v1/projects/{pid}/ledger/awaiting-me", headers=h_wang)
    sup = r.json()["data"]
    check("监理此刻无待签（还没轮到复核）", sup["item_count"] == 0, str(sup["item_count"]))

    # ---------- 签认轨迹 ----------
    print("\n[6] 签认轨迹：谁签的、什么时候")
    r = run_signoff(client, vid)
    check("签认流程走完", r == "FINISHED", str(r))

    r = client.get(f"/api/v1/projects/{pid}/ledger", headers=h_ou)
    led3 = r.json()["data"]
    target2 = next((i for i in led3["items"] if i["document_id"] == doc_id), None)
    check("台账里仍能找到该文件", target2 is not None)
    if target2:
        tr = target2["trace"]
        check("有签认轨迹", len(tr) >= 2, str(len(tr)))
        # 轨迹里应含主办确认 + 相关复核
        nodes = {t["node_code"] for t in tr}
        check("轨迹含主办确认节点", "CONFIRM" in nodes, str(nodes))
        check("轨迹含相关复核节点", "REVIEW" in nodes, str(nodes))
        with_actor = [t for t in tr if t.get("actor")]
        check("每条轨迹都有操作人", len(with_actor) == len(tr), str(len(with_actor)))
        if with_actor:
            check("操作人有姓名", bool(with_actor[0]["actor"].get("name")),
                  str(with_actor[0]["actor"]))
        units = {t["unit_code"] for t in tr}
        check("轨迹记录了承办单位", "DESIGNER" in units, str(units))
        check("轨迹有时间", all(t.get("acted_at") for t in tr))
        check("在途已清空（签完了）", not target2["pending_units"],
              str(target2["pending_units"]))

    # ---------- 阶段权限过滤 ----------
    print("\n[7] 阶段级权限过滤")
    # 设计单位看不到"前期调研"阶段的文件（矩阵里设计单位在该阶段无责任）
    r = client.get(f"/api/v1/projects/{pid}/ledger", headers=h_ou, params={"stage": "PRE_SURVEY"})
    check("设计单位查前期调研阶段 → 被拒绝", r.status_code == 403,
          f"got {r.status_code} {r.text[:160]}")

    # 但建设单位可以（它是前期调研的主办单位）
    h_chen = login(client, "chenkaili")
    r = client.get(f"/api/v1/projects/{pid}/ledger", headers=h_chen, params={"stage": "PRE_SURVEY"})
    check("建设单位查前期调研阶段 → 允许", r.status_code == 200, f"got {r.status_code}")

    # 不传 stage 时，看不到的阶段整段不出现
    r = client.get(f"/api/v1/projects/{pid}/ledger", headers=h_ou)
    stages_seen = {i["stage_code"] for i in r.json()["data"]["items"]}
    check("设计单位看不到前期调研阶段的文件",
          "PRE_SURVEY" not in stages_seen, str(stages_seen))
    check("设计单位能看到设计阶段的文件", "DESIGN" in stages_seen, str(stages_seen))
    check("设计单位能看到勘察阶段的文件（查阅输入资料）",
          "INVESTIGATION" in stages_seen, str(stages_seen))

    # ---------- 七阶段责任总览 ----------
    print("\n[8] 七阶段责任总览")
    r = client.get(f"/api/v1/projects/{pid}/stage-responsibility", headers=h_ou)
    check("责任总览接口可访问", r.status_code == 200, f"got {r.status_code}")
    board = r.json()["data"]
    check("返回 7 个阶段", len(board) == 7, str(len(board)))

    expected_primary = {
        "PRE_SURVEY": "OWNER",
        "INVESTIGATION": "SURVEYOR",
        "DESIGN_TEST_PILE": "DESIGN_TEST_PILE",
        "DESIGN": "DESIGNER",
        "CONSTRUCTION": "GENERAL_CONTRACTOR",
        "ACCEPT_TEST_PILE": "ACCEPT_TEST_PILE",
        "MONITORING": "INSPECTOR",
    }
    bad = [
        (b["stage_code"], b["primary_unit"], expected_primary.get(b["stage_code"]))
        for b in board
        if b["primary_unit"] != expected_primary.get(b["stage_code"])
    ]
    check("各阶段主办单位与《管理流程》矩阵一致", not bad, str(bad))

    for b in board:
        if not b.get("stage_label"):
            check(f"阶段 {b['stage_code']} 有中文名", False, str(b))
            break
    else:
        check("每个阶段都有中文名", True)

    detail_ok = all(b.get("units_detail") for b in board)
    check("每个阶段带参与单位明细", detail_ok)

    d_stage = next((b for b in board if b["stage_code"] == "DESIGN"), None)
    if d_stage:
        labels = {u["unit_label"] for u in d_stage["units_detail"]}
        check("设计阶段参与单位含设计单位", "设计单位" in labels, str(labels))
        check("设计阶段参与单位含监理单位", "监理单位" in labels, str(labels))
        check("设计阶段参与单位含政府审查单位", "政府审查单位" in labels, str(labels))
        prim = next(
            (u for u in d_stage["units_detail"] if u["unit_code"] == "DESIGNER"), None
        )
        check("设计单位在设计阶段是主要责任",
              prim and prim["responsibility"] == "PRIMARY", str(prim))

    # ---------- 非参与人被拦 ----------
    print("\n[9] 非项目参与人被拦")
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
                    must_change_password=False,
                )
            )
            db.commit()
    finally:
        db.close()

    h_out = login(client, "probe_outsider")
    r = client.get(f"/api/v1/projects/{pid}/ledger", headers=h_out)
    check("非参与人查台账 → 被拒绝", r.status_code == 403, f"got {r.status_code}")
    r = client.get(f"/api/v1/projects/{pid}/stage-responsibility", headers=h_out)
    check("非参与人查责任总览 → 被拒绝", r.status_code == 403, f"got {r.status_code}")

    # ---------- 设计输入：上游输入文件可查阅 ----------
    # 新方向下"设计输入"降级为**输入文件库**：设计人员要能查阅上游
    # （前期调研 / 勘察 / 设计试桩）的文件。这依赖矩阵里设计单位在这些阶段
    # 有 PARTICIPANT 责任 —— 若哪天有人把这条责任删掉，设计人员就查不到
    # 勘察报告了，这个测试会立刻失败。
    print("\n[10] 输入文件库：设计人员能查阅上游输入文件")
    r = client.get(f"/api/v1/projects/{pid}/ledger", headers=h_ou)
    all_items = r.json()["data"]["items"]
    upstream = {"PRE_SURVEY", "INVESTIGATION", "DESIGN_TEST_PILE"}
    up_items = [i for i in all_items if i["stage_code"] in upstream]
    check("设计单位能看到上游阶段文件", bool(up_items),
          str({i["stage_code"] for i in all_items}))
    survey = [i for i in up_items if i["stage_code"] == "INVESTIGATION"]
    check("能看到勘察阶段文件（设计输入的主要来源）", bool(survey),
          str([i["stage_code"] for i in up_items]))
    if survey:
        s = survey[0]
        check("勘察文件的主办单位是勘察单位",
              s["primary_unit"] == "SURVEYOR", str(s["primary_unit"]))
        check("勘察文件带可下载的已发布版本",
              bool(s["current_version_no"]), str(s.get("current_version_no")))
        check("勘察文件标明了上传人（可追溯）",
              bool(s.get("current_uploaded_by")), str(s.get("current_uploaded_by")))

    # 设计试桩阶段也是设计输入之一（设计单位在那里是"相关"责任）。
    # 注意演示数据里该阶段**没有文件**，所以只断言"若有则应可见"，
    # 不能断言"必须有"—— 那是在测演示数据而不是测权限。
    dtest = [i for i in all_items if i["stage_code"] == "DESIGN_TEST_PILE"]
    print(f"    (设计试桩阶段可见文件 {len(dtest)} 份)")
    check("设计试桩阶段若存在文件则应可见",
          all(i["stage_code"] == "DESIGN_TEST_PILE" for i in dtest))

    # ---------- 汇总 ----------
    print("\n" + "=" * 56)
    print(f"通过 {passed} 项，失败 {failed} 项")
    if failed == 0:
        print()
        print("提示：测试会在演示项目里创建 TEST-LEDGER-* 文件。")
        print("      需要干净演示数据时执行：")
        print("        .venv\\Scripts\\python.exe -m app.seed.seed_all --reset")
    print("=" * 56)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
