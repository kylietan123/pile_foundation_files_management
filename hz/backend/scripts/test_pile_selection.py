"""桩基选型（设计阶段）测试。

覆盖两层：
  1. 规则引擎 —— 沿用桌面「选型」软件 test_selection.py 的经典用例，
     保证移植后结论不变（经济场景→PHC、地铁保护区→端注浆、桩径规则、线插法）；
  2. 接口 —— 试算 / 保存 / 读回 / 权限边界（非设计阶段责任单位不能保存）。

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/test_pile_selection.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import pile_selection as engine  # noqa: E402

PASSWORD = "Tjad@2026"
passed = 0
failed = 0


def check(desc: str, cond: bool, extra: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {desc}")
    else:
        failed += 1
        print(f"  [FAIL] {desc}  {extra}")


# ---- 场景条件：古美（无限制，地下2层） ----
GUMEI = {
    "metro_protection_zone": False, "inner_ring": False,
    "near_viaduct_bridge": False, "dense_buildings_nearby": False,
    "noise_sensitive": False, "tight_schedule": False,
    "tight_budget": False, "env_protection_strict": False,
    "has_sand_layer": False, "basement_floors": 2,
    "need_permanent_temp_combo": False, "has_inner_support": False,
}


def test_engine() -> None:
    print("\n[1] 规则引擎（原软件用例回归）")
    s = engine.suggest(GUMEI, None)
    check("经济场景 主楼建议 PHC", s["main"]["type_name"] == "PHC预应力混凝土管桩",
          s["main"]["type_name"])
    check("经济场景 地下室建议 PHC", s["base"]["type_name"] == "PHC预应力混凝土管桩",
          s["base"]["type_name"])
    check("经济场景 主楼无排除", s["main"]["excluded"] == [], str(s["main"]["excluded"]))
    check("根植桩在地下室被排除",
          any(r["name"] == "根植桩" for r in s["base"]["excluded"]))
    check("场景标记为 economy", s["scenario"] == "economy")
    check("PHC 主楼典型参数 190t", s["main"]["params"]["capacity_t"] == 190,
          str(s["main"]["params"]))
    check("PHC 主楼典型参数 46m/42m", s["main"]["params"]["lengths"] == "46m/42m")
    check("PHC 主楼持力层 ⑦₂", s["main"]["params"]["layer"] == "⑦₂")

    # 优选桩型排序：端注浆排在普通灌注桩与方桩之前
    order = [r["name"] for r in s["main"]["ranking"]
             if not r["hard_excluded"] and not r["not_considered"]]
    check("优选桩型：端注浆排在普通灌注桩前",
          order.index("钻孔灌注桩(端注浆)") < order.index("钻孔灌注桩"), str(order))

    # 地铁保护区 → 受限场景，挤土桩全部排除
    meilong = dict(GUMEI, metro_protection_zone=True)
    s2 = engine.suggest(meilong, None)
    check("受限场景 主楼建议 端注浆", s2["main"]["type_name"] == "钻孔灌注桩(端注浆)",
          s2["main"]["type_name"])
    check("受限场景 地下室建议 端注浆", s2["base"]["type_name"] == "钻孔灌注桩(端注浆)")
    check("受限场景 挤土桩全部排除",
          all(r["hard_excluded"] for r in s2["main"]["ranking"]
              if r["name"] in engine.R.DISPLACEMENT_PILES))
    check("受限场景标记为 restricted", s2["scenario"] == "restricted")
    check("排除原因含『必须选用非挤土桩』",
          any("必须选用非挤土桩" in r["reason"] for r in s2["main"]["excluded"]))

    # UHC 暂不参与选型，但仍在候选列表里
    uhc = [r for r in s["main"]["ranking"] if r["name"] == "UHC高性能管桩"]
    check("UHC 仍在候选中且标记 not_considered",
          len(uhc) == 1 and uhc[0]["not_considered"] and not uhc[0]["hard_excluded"])

    # 含砂层不再排除 PHC
    s_sand = engine.suggest(dict(GUMEI, has_sand_layer=True), None)
    check("含砂层 主楼仍建议 PHC", s_sand["main"]["type_name"] == "PHC预应力混凝土管桩")
    check("含砂层 无排除项", s_sand["main"]["excluded"] == [])

    # 高度带
    check("高度带 5F→低多层", engine.height_band({"tower_max_floors": 5}) == 0)
    check("高度带 8F→中高层", engine.height_band({"tower_max_floors": 8}) == 1)
    check("高度带 20F→高层", engine.height_band({"tower_max_floors": 20}) == 2)
    check("高度带 120m→超高层", engine.height_band({"tower_max_height_m": 120}) == 3)
    check("高度带 无信息→None", engine.height_band({}) is None)

    # 桩径规则
    check("桩径规则 20F 非受限 PHC→500",
          engine.rule_diameter("PHC预应力混凝土管桩", "main",
                               {"tower_max_floors": 20}) == 500)
    check("桩径规则 20F 地铁 端注浆→800（图内直标）",
          engine.rule_diameter("钻孔灌注桩(端注浆)", "main",
                               {"tower_max_floors": 20, "metro_protection_zone": True}) == 800)
    check("桩径规则 B2 地下室 PHC→500",
          engine.rule_diameter("PHC预应力混凝土管桩", "base",
                               {"basement_floors": 2}) == 500)

    # 勘察表行匹配与线插法
    geo = {"capacity_rows": [
        {"pile_type_desc": "Ф800钻孔灌注桩", "d_mm": 800, "length_m": 41.8,
         "bearing_layer_id": "⑦₂", "ra_kn": 2270, "note": "后注浆"},
    ]}
    p = engine.pick_params("钻孔灌注桩(端注浆)", "main", meilong, geo)
    check("勘察行匹配 桩径800", p["d_mm"] == 800, str(p))
    check("勘察行匹配 承载力390t（2270kN×1.72）", p["capacity_t"] == 390, str(p.get("capacity_t")))
    check("勘察行匹配 桩长42m", p["lengths"] == "42m", str(p.get("lengths")))
    check("勘察行匹配 from_row=True", p.get("from_row") is True)

    p_phc = engine.pick_params("PHC预应力混凝土管桩", "main", GUMEI, geo)
    check("PHC 不匹配灌注桩行（走典型组合）",
          p_phc["capacity_t"] == 190 and not p_phc.get("from_row"))

    # 两行不同直径 → 规则桩径无对应行时线插
    geo2 = {"capacity_rows": [
        {"pile_type_desc": "Ф800钻孔灌注桩", "d_mm": 800, "length_m": 45.0,
         "bearing_layer_id": "⑦₂", "rd_kn": 3480},
        {"pile_type_desc": "Ф600钻孔灌注桩", "d_mm": 600, "length_m": 35.0,
         "bearing_layer_id": "⑦₁", "rd_kn": 2400},
    ]}
    p_int = engine.pick_params("钻孔灌注桩(端注浆)", "main",
                               {"tower_max_floors": 20}, geo2)
    check("规则桩径无对应行 → 线插并标记 from_interp", p_int.get("from_interp") is True, str(p_int))
    check("线插结果落在 348t 与 240t 之间",
          p_int.get("capacity_t") is not None and 240 <= p_int["capacity_t"] <= 348,
          str(p_int.get("capacity_t")))

    # 设计值直用（不再叠加后注浆系数）
    geo3 = {"capacity_rows": [
        {"pile_type_desc": "Ф800钻孔灌注桩（桩端后注浆）", "d_mm": 800, "length_m": 45.0,
         "bearing_layer_id": "⑦₂", "rd_kn": 3480},
    ]}
    p3 = engine.pick_params("钻孔灌注桩(端注浆)", "main", meilong, geo3)
    check("设计值直用 348t（3480/10，不乘1.72）", p3["capacity_t"] == 348, str(p3.get("capacity_t")))

    # 选型理由
    reason = engine.build_reason(meilong, "钻孔灌注桩(端注浆)", "钻孔灌注桩")
    check("受限场景理由含『地铁50m安全保护区』", "地铁50m安全保护区" in reason, reason)
    reason2 = engine.build_reason(GUMEI, "PHC预应力混凝土管桩", None)
    check("经济场景理由说明不在保护区内", "不在地铁50m安全保护区范围内" in reason2, reason2)


def _login(client: TestClient, username: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _project(client: TestClient, headers: dict, keyword: str) -> dict:
    rows = client.get("/api/v1/projects", headers=headers).json().get("data") or []
    hit = next((p for p in rows if keyword in (p.get("name") or "")), None)
    assert hit is not None, f"没有找到包含「{keyword}」的项目：{[p['name'] for p in rows]}"
    return hit


def test_api() -> None:
    print("\n[2] 接口：试算 / 保存 / 读回")
    client = TestClient(app)
    h = _login(client, "ouyuxin")            # 设计单位，杭州/上海项目里是设计阶段主办
    hz = _project(client, h, "杭州")          # 设计单位身份
    sz = _project(client, h, "苏州")          # 勘察单位身份（设计阶段只有参与权）

    r = client.get(f"/api/v1/projects/{hz['id']}/pile-selection/options", headers=h)
    opts = r.json().get("data") or {}
    check("桩型选项接口 200", r.status_code == 200, r.text[:200])
    check("桩型选项含 7 种桩型", len(opts.get("pile_types") or []) == 7,
          str(len(opts.get("pile_types") or [])))
    check("条件说明含地铁保护区", any(
        c["key"] == "metro_protection_zone" and c["hard"]
        for c in opts.get("conditions") or []))

    body = {"conditions": GUMEI, "geo": None}
    # 「试算不落库」要按"记录有没有变"来判，而不是假设一开始没有记录
    # （否则重复跑本脚本时，上一次留下的方案会让这条断言假失败）
    before = client.get(f"/api/v1/projects/{hz['id']}/pile-selection",
                        headers=h).json().get("data")
    r = client.post(f"/api/v1/projects/{hz['id']}/pile-selection/suggest", headers=h, json=body)
    sug = r.json().get("data") or {}
    check("试算接口 200", r.status_code == 200, r.text[:200])
    check("试算主楼建议 PHC", sug.get("main", {}).get("type_name") == "PHC预应力混凝土管桩",
          str(sug.get("main", {}).get("type_name")))
    check("试算返回排序明细", len(sug.get("main", {}).get("ranking") or []) == 7)
    check("无勘察数据时 basis=typical（明确告知只是典型组合）",
          sug.get("basis") == "typical", str(sug.get("basis")))
    check("无勘察数据时主楼参数来自典型组合",
          sug.get("main", {}).get("params", {}).get("from_row") is False)

    sc = {"conditions": {**GUMEI, "metro_protection_zone": True}, "geo": None}
    r = client.post(f"/api/v1/projects/{hz['id']}/pile-selection/suggest", headers=h, json=sc)
    sug2 = r.json().get("data") or {}
    check("地铁保护区场景 主楼→端注浆",
          sug2.get("main", {}).get("type_name") == "钻孔灌注桩(端注浆)")
    after = client.get(f"/api/v1/projects/{hz['id']}/pile-selection",
                       headers=h).json().get("data")
    check("试算不落库（记录未被创建/改动）",
          (before or {}).get("id") == (after or {}).get("id"), "试算后记录变了")

    save = {
        "conditions": GUMEI,
        "geo": None,
        "main": {"type_name": "PHC预应力混凝土管桩",
                 "params": {"desc": "PHC 500（125）AB 管桩", "short": "PHC 500（125）AB",
                            "d_mm": 500, "lengths": "46m/42m", "capacity_t": 190,
                            "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"}},
        "base": {"type_name": "PHC预应力混凝土管桩",
                 "params": {"desc": "PHC 400（95）AB 管桩", "short": "PHC 400（95）AB",
                            "d_mm": 400, "lengths": "26m", "uplift_t": 50,
                            "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"}},
        "status": "DRAFT",
    }
    r = client.put(f"/api/v1/projects/{hz['id']}/pile-selection", headers=h, json=save)
    check("保存草稿 200", r.status_code == 200, r.text[:300])
    saved = r.json().get("data") or {}
    check("保存后状态 DRAFT", saved.get("status") == "DRAFT")
    check("保存后主楼桩型正确",
          (saved.get("main") or {}).get("type_name") == "PHC预应力混凝土管桩")
    check("保存时自动生成选型理由", bool(saved.get("reason")), str(saved.get("reason"))[:60])
    check("保存时冻结引擎建议快照", bool(saved.get("snapshot")))

    # 没有勘察依据时**不允许确认**（选型是设计依据性结论）
    r = client.put(f"/api/v1/projects/{hz['id']}/pile-selection", headers=h,
                   json={**save, "status": "CONFIRMED"})
    check("无勘察依据时确认被拒绝", r.status_code == 400, str(r.status_code))
    check("拒绝提示说明缺勘察依据",
          "勘察" in r.text and "依据" in r.text, r.text[:200])

    r = client.get(f"/api/v1/projects/{hz['id']}/pile-selection", headers=h)
    got = r.json().get("data") or {}
    check("读回方案与保存一致",
          (got.get("main") or {}).get("type_name") == "PHC预应力混凝土管桩", str(got)[:200])

    # 录入勘察承载力表后 → 有依据，可以确认
    geo_rows = {"capacity_rows": [
        {"pile_type_desc": "PHC 500 AB 管桩", "d_mm": 500, "length_m": 46,
         "bearing_layer_id": "⑦₂", "ra_kn": 1900},
        {"pile_type_desc": "PHC 400 AB 管桩", "d_mm": 400, "length_m": 26,
         "bearing_layer_id": "⑦₂", "ra_kn": 1000, "rtd_kn": 500},
    ]}
    save_geo = {**save, "geo": geo_rows, "status": "CONFIRMED"}
    r = client.put(f"/api/v1/projects/{hz['id']}/pile-selection", headers=h, json=save_geo)
    conf = r.json().get("data") or {}
    check("有勘察依据后可以确认", r.status_code == 200 and conf.get("status") == "CONFIRMED",
          r.text[:300])
    check("确认人与确认时间已记录",
          bool(conf.get("confirmed_by")) and bool(conf.get("confirmed_at")))
    check("有勘察依据的快照 basis=survey",
          ((conf.get("snapshot") or {}).get("basis")) == "survey",
          str((conf.get("snapshot") or {}).get("basis")))

    print("\n[3] 权限边界")
    r = client.put(f"/api/v1/projects/{sz['id']}/pile-selection", headers=h, json=save)
    check("非设计阶段责任单位不能保存选型", r.status_code == 403, str(r.status_code))
    check("403 提示说明阶段身份",
          "参与" in r.text or "无权" in r.text, r.text[:200])

    r = client.get(f"/api/v1/projects/{sz['id']}/pile-selection/options", headers=h)
    check("但可以查看本项目选型（参与单位有查看权）", r.status_code == 200, str(r.status_code))

    # 未登录不能访问
    r = client.post(f"/api/v1/projects/{hz['id']}/pile-selection/suggest", json=body)
    check("未登录不能试算", r.status_code == 401, str(r.status_code))


def main() -> int:
    test_engine()
    test_api()
    print(f"\n桩基选型：通过 {passed} 项，失败 {failed} 项")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
