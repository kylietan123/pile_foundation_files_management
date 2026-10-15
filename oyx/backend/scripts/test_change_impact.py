"""设计变更影响分析 —— 专项测试。

重点验证的不是"接口能返回数据"，而是**影响分析算得对不对**：

  1. 六类影响是否都能识别（桩位 / 已施工部位 / 计算书 / 图纸 / 成本 / 进度）
  2. **「已施工部位受影响」这个最高风险项是否被正确识别**
     —— 这是安全价值的落点，也是通用文档系统做不到的
  3. 未做影响分析不允许提交审批（防止审批人无法判断范围）
  4. 影响明细未全部处理不允许关闭变更（防止"批了但没执行"的漏洞）
  5. 按分区筛选是否准确

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/test_change_impact.py
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
    h_chen = login(client, "chenkaili")
    h_zw = login(client, "chenkaili")   # 张伟已不在演示账号中，改用建设单位
    h_hx = login(client, "haoxirui")

    # ---------- 准备 ----------
    print("\n[0] 准备：项目与桩位数据")
    r = client.get("/api/v1/projects", headers=h_ou)
    hz = next((p for p in r.json()["data"] if "杭州" in p["name"]), None)
    check("找到杭州项目", hz is not None)
    if not hz:
        return 1
    hz_id = hz["id"]

    # 桩位分区分布：1#楼 与 2#楼 已施工，商业裙房未施工
    r = client.get(f"/api/v1/projects/{hz_id}/changes", headers=h_ou)
    check("变更列表可访问", r.status_code == 200, f"got {r.status_code}")
    seeded = r.json()["data"]
    check("种子变更为 3 条", len(seeded) == 3, f"got {len(seeded)}")
    if seeded:
        bg002 = next((c for c in seeded if c["change_no"].endswith("002")), None)
        if bg002:
            print(f"    (BG-002: state={bg002['state']} impact_total={bg002['impact_total']} "
                  f"impacts={len(bg002['impacts'])})")
            check("种子变更带影响明细", len(bg002["impacts"]) > 0, str(len(bg002["impacts"])))
            check("种子变更标记了已施工部位影响",
                  bg002["has_constructed_impact"] is True,
                  str(bg002.get("has_constructed_impact")))

    # ---------- 新建变更并做影响分析 ----------
    print("\n[1] 新建变更 + 执行影响分析（范围：1#楼，已施工）")
    r = client.post(
        f"/api/v1/projects/{hz_id}/changes",
        headers=h_ou,
        json={
            "stage_code": "DESIGN",
            "title": "1#楼桩顶标高按建筑图 V3 调整",
            "category": "SITE_CONDITION",
            "reason": "建筑图 V3 将承台顶标高由 +2.800 调整为 +2.600，桩顶标高需相应下调 0.2m。",
        },
    )
    check("发起变更返回 200", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")
    change = r.json()["data"]
    change_id = change["id"]
    check("变更编号自动生成", (change["change_no"] or "").startswith("BG-"), change.get("change_no"))
    check("初始状态为待提交", change["state"] == "DRAFT", change.get("state"))
    check("尚未分析时无影响明细", change["impact_total"] == 0, str(change["impact_total"]))
    check("状态标签为中文", change["state_label"] == "待提交", str(change.get("state_label")))
    check("变更原因分类有中文标签", change["category_label"] == "施工条件", str(change.get("category_label")))

    # 未分析就提交 → 必须被拒
    r = client.post(f"/api/v1/projects/{hz_id}/changes/{change_id}/submit", headers=h_ou)
    check("未做影响分析就提交审批 → 被拒绝", r.status_code == 400,
          f"got {r.status_code} {r.text[:200]}")
    if r.status_code == 400:
        check("拒绝原因提示需先做影响分析",
              "影响分析" in r.json()["message"], r.json().get("message"))

    # 执行分析（1#楼已施工）
    r = client.post(
        f"/api/v1/projects/{hz_id}/changes/{change_id}/analyze",
        headers=h_ou,
        json={"scope_zones": ["1#楼"]},
    )
    check("影响分析返回 200", r.status_code == 200, f"got {r.status_code} {r.text[:300]}")
    change = r.json()["data"]
    msg = r.json()["message"]
    print(f"    (分析结果: {msg})")

    check("分析后状态变为影响分析中",
          change["state"] == "IMPACT_ANALYZING", change.get("state"))
    check("生成影响明细", change["impact_total"] > 0, str(change["impact_total"]))

    types = {i["target_type"] for i in change["impacts"]}
    print(f"    (识别出的影响类型: {sorted(types)})")

    # 六类影响
    check("识别出「受影响桩位」", "PILE" in types, str(types))
    check("识别出「已施工部位」（最高风险）", "CONSTRUCTED_PART" in types, str(types))
    check("识别出「计算书」", "CALCULATION" in types, str(types))
    check("识别出「图纸」", "DRAWING" in types, str(types))
    check("识别出「成本」", "COST" in types, str(types))
    check("识别出「进度」", "SCHEDULE" in types, str(types))

    # 已施工部位必须标记需立即通知
    cp = next((i for i in change["impacts"] if i["target_type"] == "CONSTRUCTED_PART"), None)
    check("已施工部位影响存在", cp is not None)
    if cp:
        check("已施工部位标记「需立即通知」",
              cp["requires_immediate_notice"] is True, str(cp))
        check("已施工部位风险等级为 HIGH", cp["severity"] == "HIGH", cp.get("severity"))
        check("已施工部位类型有中文标签",
              cp["target_type_label"] == "已施工部位", str(cp.get("target_type_label")))
        print(f"    (已施工部位描述: {cp['impact_desc'][:70]}...)")

    check("变更汇总记录了受影响桩数", change["impact_pile_count"] > 0, str(change["impact_pile_count"]))
    check("变更汇总记录了已施工桩数", change["impact_constructed_count"] > 0,
          str(change["impact_constructed_count"]))
    check("变更汇总记录了成本影响", change["impact_cost_delta"] is not None,
          str(change.get("impact_cost_delta")))
    check("变更汇总记录了工期影响", change["impact_schedule_days"] is not None,
          str(change.get("impact_schedule_days")))
    check("变更标记了存在已施工影响", change["has_constructed_impact"] is True, str(change))

    # 分析消息应提示已施工部位
    check("分析消息提示需立即通知",
          "已施工" in msg and "通知" in msg, msg)

    # ---------- 受影响桩位清单 ----------
    print("\n[2] 受影响桩位清单")
    r = client.get(f"/api/v1/projects/{hz_id}/changes/{change_id}/affected-piles", headers=h_ou)
    check("受影响桩位接口返回 200", r.status_code == 200, f"got {r.status_code}")
    piles = r.json()["data"]
    check("返回桩位清单", len(piles) > 0, f"got {len(piles)}")
    if piles:
        zones = {p["zone"] for p in piles}
        check("桩位限定在指定分区（仅 1#楼）", zones == {"1#楼"}, str(zones))
        statuses = {p["status"] for p in piles}
        check("分区内桩位均为已施工状态", statuses == {"CONSTRUCTED"}, str(statuses))

    r = client.get(
        f"/api/v1/projects/{hz_id}/changes/{change_id}/affected-piles",
        headers=h_ou,
        params={"only_constructed": True},
    )
    check("可按仅已施工筛选", r.status_code == 200, f"got {r.status_code}")
    check("筛选后数量一致", len(r.json()["data"]) == len(piles), f"{len(r.json()['data'])} vs {len(piles)}")

    # ---------- 重新分析（换范围）----------
    print("\n[3] 重新分析：改为未施工的「商业裙房」")
    r = client.post(
        f"/api/v1/projects/{hz_id}/changes/{change_id}/analyze",
        headers=h_ou,
        json={"scope_zones": ["商业裙房"]},
    )
    check("重新分析返回 200", r.status_code == 200, f"got {r.status_code}")
    change2 = r.json()["data"]
    types2 = {i["target_type"] for i in change2["impacts"]}
    check("重新分析替换了旧结果（无已施工部位）", "CONSTRUCTED_PART" not in types2, str(types2))
    check("重新分析后已施工桩数为 0", change2["impact_constructed_count"] == 0,
          str(change2["impact_constructed_count"]))
    check("重新分析后标记不再有已施工影响", change2["has_constructed_impact"] is False, str(change2))
    check("影响明细数量未累加（替换而非追加）",
          change2["impact_total"] <= change["impact_total"] + 1,
          f"{change2['impact_total']} vs {change['impact_total']}")

    # 换回 1#楼，继续保持已施工场景用于后续流程测试
    r = client.post(
        f"/api/v1/projects/{hz_id}/changes/{change_id}/analyze",
        headers=h_ou,
        json={"scope_zones": ["1#楼"]},
    )
    change = r.json()["data"]
    check("换回 1#楼后重新识别出已施工部位",
          change["has_constructed_impact"] is True, str(change))

    # ---------- 提交审批 ----------
    print("\n[4] 提交变更审批")
    r = client.post(f"/api/v1/projects/{hz_id}/changes/{change_id}/submit", headers=h_ou)
    check("提交审批成功", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")
    change = r.json()["data"]
    check("状态变为审批中", change["state"] == "APPROVING", change.get("state"))
    check("生成了流程实例", bool(change["workflow_instance_id"]), str(change))
    # 提交人是设计单位（主办），首节点 IMPACT 被跳过，直接进 REVIEW（监理+政府）。
    # 所以**提交人自己没有待签任务**，available_actions 为空是正确的。
    check("提交人无待签任务（首节点已跳过）",
          change["available_actions"] == [] or "approve" not in change["available_actions"],
          str(change.get("available_actions")))

    # 已提交后不允许再分析
    r = client.post(
        f"/api/v1/projects/{hz_id}/changes/{change_id}/analyze",
        headers=h_ou,
        json={"scope_zones": ["1#楼"]},
    )
    check("审批中不允许再执行影响分析", r.status_code == 400, f"got {r.status_code}")

    # ---------- 审批通过 ----------
    print("\n[5] 审批通过")
    r = client.get(f"/api/v1/tasks/instances/{change['workflow_instance_id']}", headers=h_ou)
    check("可查变更审批轨迹", r.status_code == 200, f"got {r.status_code}")

    # 变更流程（新模型）：首节点 IMPACT 由发起人完成、启动时跳过，
    # 所以实际只有 REVIEW 节点，由**相关单位**复核 ——
    # 设计阶段的相关单位是 监理单位 + 政府审查单位，并行派任务，都签完才算通过。
    h_wang = login(client, "wangwu")   # 监理单位
    h_gong = login(client, "gongwu")   # 政府审查单位
    UNIT_ACTOR = {
        "SUPERVISOR": ("监理单位", h_wang),
        "GOVERNMENT": ("政府审查单位", h_gong),
        "DESIGNER": ("设计单位", h_ou),
    }
    for i in range(8):
        r = client.get(f"/api/v1/tasks/instances/{change['workflow_instance_id']}", headers=h_ou)
        tr = r.json()["data"]
        if tr["status"] == "FINISHED":
            print(f"    (流程在第 {i} 轮结束)")
            break
        task = next((t for t in tr["tasks"] if t["action"] is None), None)
        if task is None:
            break
        actor_name, actor_h = UNIT_ACTOR.get(
            task.get("assignee_role"), ("设计单位", h_ou)
        )
        r2 = client.post(
            f"/api/v1/projects/{hz_id}/changes/{change_id}/decide",
            headers=actor_h,
            json={"action": "APPROVE", "comment": f"{actor_name} 复核同意"},
        )
        print(f"    (节点 {task['node_code']} 由 {actor_name} 处理: {r2.status_code})")
        if r2.status_code != 200:
            print(f"        失败原因: {r2.json().get('message')}")
            print(f"      -> {r2.json().get('message')}")
            break

    r = client.get(f"/api/v1/projects/{hz_id}/changes/{change_id}", headers=h_ou)
    change = r.json()["data"]
    check("审批通过后状态为执行中", change["state"] == "EXECUTING", change.get("state"))
    check("记录了批准时间", change["approved_at"] is not None, str(change.get("approved_at")))

    # ---------- 关闭互锁 ----------
    print("\n[6] 关闭互锁：影响未处理完不允许关闭")
    r = client.post(f"/api/v1/projects/{hz_id}/changes/{change_id}/close", headers=h_ou)
    check("影响未处理完就关闭 → 被拒绝", r.status_code == 400,
          f"got {r.status_code} {r.text[:200]}")
    if r.status_code == 400:
        check("拒绝原因提示还有影响未处理",
              "影响未处理" in r.json()["message"] or "未处理" in r.json()["message"],
              r.json().get("message"))

    # 处理影响项：不填说明 → 拒绝
    first_impact = change["impacts"][0]
    r = client.post(
        f"/api/v1/projects/{hz_id}/changes/{change_id}/impacts/{first_impact['id']}/handle",
        headers=h_ou,
        json={"note": ""},
    )
    check("处理影响不填说明 → 被拒绝", r.status_code == 422 or r.status_code == 400,
          f"got {r.status_code}")

    # 逐项处理
    r = client.get(f"/api/v1/projects/{hz_id}/changes/{change_id}", headers=h_ou)
    change = r.json()["data"]
    for imp in change["impacts"]:
        if imp["handled"]:
            continue
        client.post(
            f"/api/v1/projects/{hz_id}/changes/{change_id}/impacts/{imp['id']}/handle",
            headers=h_ou,
            json={"note": "已按变更后参数更新，并已电话+书面通知施工方与监理"},
        )

    r = client.get(f"/api/v1/projects/{hz_id}/changes/{change_id}", headers=h_ou)
    change = r.json()["data"]
    check("全部影响已处理", change["impact_handled"] == change["impact_total"],
          f"{change['impact_handled']}/{change['impact_total']}")
    check("处理进度完整标记", change["impact_handled"] == change["impact_total"], str(change))

    # 通知
    print("\n[7] 通知受影响单位")
    r = client.post(f"/api/v1/projects/{hz_id}/changes/{change_id}/notify", headers=h_ou)
    check("通知接口返回 200", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    check("通知消息说明了通知对象",
          "施工方" in r.json()["message"] or "无需" in r.json()["message"],
          r.json().get("message"))

    # 关闭
    r = client.post(f"/api/v1/projects/{hz_id}/changes/{change_id}/close", headers=h_ou)
    check("影响全部处理后关闭成功", r.status_code == 200, f"got {r.status_code} {r.text[:250]}")
    if r.status_code == 200:
        change = r.json()["data"]
        check("状态变为已关闭", change["state"] == "CLOSED", change.get("state"))
        check("记录了关闭时间", change["closed_at"] is not None, str(change.get("closed_at")))

    # 已关闭不能再操作
    r = client.post(f"/api/v1/projects/{hz_id}/changes/{change_id}/analyze", headers=h_ou,
                    json={"scope_zones": ["1#楼"]})
    check("已关闭的变更不能再操作", r.status_code == 400, f"got {r.status_code}")

    # ---------- 权限边界 ----------
    print("\n[8] 权限边界：无 EDIT 权限的用户")
    h_li = login(client, "ligong")  # 勘察单位，且阶段不含 DESIGN
    r = client.post(
        f"/api/v1/projects/{hz_id}/changes",
        headers=h_li,
        json={
            "stage_code": "DESIGN",
            "title": "越权测试",
            "category": "OWNER_REQUEST",
            "reason": "测试",
        },
    )
    check("无权限用户发起变更 → 被拒绝", r.status_code == 403, f"got {r.status_code}")
    r = client.get(f"/api/v1/projects/{hz_id}/changes/{change_id}", headers=h_li)
    check("无权限用户查看变更详情的处理", r.status_code in (200, 403), f"got {r.status_code}")

    # ---------- 汇总 ----------
    print("\n" + "=" * 56)
    print(f"通过 {passed} 项，失败 {failed} 项")
    if failed == 0:
        print()
        print("提示：测试会在演示项目里创建 BG-* 变更单。")
        print("      需要干净演示数据时执行：")
        print("        .venv\\Scripts\\python.exe -m app.seed.seed_all --reset")
    print("=" * 56)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
