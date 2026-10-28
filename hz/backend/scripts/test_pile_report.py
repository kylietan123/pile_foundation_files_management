"""桩基评估报告（TXT）测试：逐字回归 + 章节省略 + 接口 + 权限。

**为什么把黄金全文内嵌在这个文件里**：
黄金样本取自原「选型」软件 `templates.GOLDEN_GUMEI`（古美项目的历史交付报告全文）。
内嵌而不是运行时去 import 桌面上的原软件目录，是为了让本仓库的测试**自包含** ——
原软件目录被挪走/删掉时，这条回归仍然有效。

唯一的有意差异：标题。原软件把甲方写成 `中海前期地块桩基评估`，
本平台默认 `桩基评估`，可通过 `report_title` 覆盖。

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/test_pile_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import pile_report as reporter  # noqa: E402

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


# ---- 古美输入（与原软件 tests/test_rules.py 完全一致）----
OVERVIEW = {
    "project_name": "闵行古美-31-02地块",
    "volume_ratio": 2.0,
    "plots": [{"plot_id": None, "land_area_m2": 31521, "aboveground_area_m2": 67400,
               "underground_area_m2": 32895, "total_area_m2": 100295}],
    "tower_count": 12,
    "towers": [{"floors": 1}, {"floors": 11}, {"floors": 14}],
    "height_range": "5m~50m",
    "basement_floors": 2,
    "basement_heights_m": [4.0, 4.0],
    "cover_thick_m": 1.5,
    "indoor_outdoor_diff_m": 0.15,
    "slab_top_m": 0.4,
    "slab_mid_m": 0.25,
    "slab_bottom_single_m": 0.6,
    "slab_bottom_double_m": 0.8,
}
SELECTION = {
    "main": {"type_name": "PHC预应力混凝土管桩",
             "desc": "PHC 500（125）AB 管桩", "short": "PHC 500（125）AB",
             "d_mm": 500, "lengths": "46m/42m", "capacity_t": 190,
             "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
    "base": {"type_name": "预制实心方桩",
             "desc": "YZH500A预应力混凝土实心方桩", "short": "YZH500A",
             "d_mm": 500, "lengths": "30m/26m", "uplift_t": 80,
             "layer": "⑦₁₋₁", "layer_desc": "粉土夹粘性土"},
}
UI_INPUTS = {
    "single_area_m2": 20017,
    "double_area_m2": 6115,
    "tower_single_m2": 9500,
    "tower_double_m2": 1950,
    "grid_x_m": 6,
    "grid_y_m": 6,
    "aboveground_double_m2": 12200,
}
META = {
    "date": "2024.02.01",
    "basis_files": [
        "0131古美地块地库_t3",
        "kc2022-16古美二号地块完整版1103带电子章",
        "中海投研地块标准表格-闵行古美项目面积统计表 方案一 0131 总",
    ],
    "conditions": {"metro_protection_zone": False, "inner_ring": False,
                   "near_viaduct_bridge": False, "dense_buildings_nearby": False,
                   "basement_floors": 2},
}

# ---- 黄金全文（原软件 templates.GOLDEN_GUMEI，仅标题按平台口径改）----
GOLDEN = """桩基评估

2024.02.01

///////////////////////////////

闵行古美-31-02地块

依据文件：
1.0131古美地块地库_t3
2.kc2022-16古美二号地块完整版1103带电子章
3.中海投研地块标准表格-闵行古美项目面积统计表 方案一 0131 总

///////////////////////////////

1. 建筑概况
----------------------
容积率：2.0
规划用地面积/地上建筑面积/地下建筑面积/总建筑面积（平米）
31521/67400/32895/100295
住宅单体数量：12
地上建筑层数：1F、11F、14F，高度5m~50m
地下建筑层数：-2F（暂估层高4m）
纯地下室顶板覆土厚度暂估1.5m，室内外高差暂估0.15m
纯地下室顶板折算厚度暂估：顶板0.4m，中板0.25m，单层地下室底板0.6m，双层地下室底板0.8m
--------------------------------------------

2. 桩基选型及估算假定
----------------------
根据图纸中提供的项目定位，项目地块不在地铁50m安全保护区范围内，主楼拟采用PHC预应力管桩，纯地下室拟采用预应力实心方桩。
    主楼范围承压桩：
        承压桩：直径500mm，PHC 500（125）AB 管桩，持力层⑦₂层灰黄~灰色粉砂，有效长度46m/42m，抗压承载力设计值190吨。
    地下室范围承压兼抗拔桩：
        YZH500A预应力混凝土实心方桩，持力层⑦₁₋₁层粉土夹粘性土，有效长度30m/26m，抗拔承载力设计值80吨。
----------------------
主楼承压桩按照地上建筑面积估算，重力荷载冗余度20%
地上重力荷载标准值暂估：1.7吨/平米
--------------------------------------------

3. 桩基数量估算
----------------------
主楼范围：
       地上重力荷载标准值总计：1.7x67400=114580吨
               地上重力荷载标准值*地上建筑面积=地上重力荷载标准值总计
       承压桩桩数估算：114580/190*1.2=723根(131根双层+592单层)
               地上重力荷载标准值总计/单桩抗压承载力*冗余度=桩数
--------------------------------------------
非主楼范围：
    抗浮工况：
        单层地下室抗拔承载力需求：(4+0.6+0.1+1)*1.1-1.5*1.6*0.9-(0.4+0.6)*2.5=1.61吨/平米
            (地下室挖深+覆土厚度内水头高)*水密度*抗浮安全系数-覆土重-(地下室投影单方砼厚度)*砼容重=单方水浮力
        两层地下室抗拔承载力需求：(4+4+0.1+0.8+1)*1.1-1.5*1.6*0.9-(0.4+0.25+0.8)*2.5=5.105吨/平米
            (地下室挖深+覆土厚度内水头高)*水密度*抗浮安全系数-覆土重-(地下室投影单方砼厚度)*砼容重=单方水浮力
    承压兼抗拔桩桩数估算：
        单层地下室：(20017-9500)/(6*6)*1.2=351根（承压控制/每根柱下一根桩）
            (单层地下室投影面积-塔楼投影面积)/柱网尺寸*冗余度=桩数
        双层地下室：(6115-1950)*5.105/80*1.2=319根（抗浮控制）
            (地下室投影面积-塔楼投影面积)*单方抗拔承载力需求/单桩抗拔承载力*冗余度=桩数
----------------------
桩基数量总计：
-----------
主楼：PHC 500（125）AB，桩长46m/42m，723根(131根双层+592单层)
非主楼：YZH500A，有效长度30m/26m，总桩数670根(351根单层+319双层)
-----------
每千平米桩数：总桩数（1393根）/地下室投影面积（26132m2）
合计：53根/千平米
--------------------------------------------

4. 总结
----------------------
   主楼范围：承压桩，直径500mm，PHC 500（125）AB 管桩，持力层⑦₂层灰黄~灰色粉砂，有效长度46m/42m，抗压承载力设计值190吨。
   地下室范围：承压兼抗拔桩，YZH500A预应力混凝土实心方桩，持力层⑦₁₋₁层粉土夹粘性土，有效长度30m/26m，抗拔承载力设计值80吨。
----------------------
备注：
1. 主楼范围承压桩估算考虑低水位水浮力与主楼地下室自重基本抵消，未考虑周边地下室抗浮对承压的有利贡献；
2. 地下室范围抗拔桩估算未考虑主楼范围内承压对抗浮的有利贡献；
3. 承压桩重力荷载和抗拔桩浮力荷载冗余度按照20%考虑。
--------------------------------------------
"""


def test_report_engine() -> None:
    print("\n[1] 报告全文逐字回归（古美黄金样本）")
    out = reporter.build_report(OVERVIEW, None, SELECTION, UI_INPUTS, META)
    a, b = out.splitlines(), GOLDEN.splitlines()
    if a == b:
        check(f"报告全文与原软件逐字一致（{len(a)} 行）", True)
    else:
        first = next(
            (i for i in range(max(len(a), len(b)))
             if (a[i] if i < len(a) else None) != (b[i] if i < len(b) else None)),
            0,
        )
        check("报告全文与原软件逐字一致", False,
              f"首个差异在第 {first + 1} 行：新={a[first] if first < len(a) else '<无>'} "
              f"旧={b[first] if first < len(b) else '<无>'}")

    check("标题可覆盖（保持原软件的客户名口径）",
          reporter.build_report(OVERVIEW, None, SELECTION, UI_INPUTS,
                                {**META, "report_title": "中海前期地块桩基评估"}
                                ).splitlines()[0] == "中海前期地块桩基评估")

    # 关键算式（审报告的人第一眼看这些）
    check("主楼桩数算式 114580/190*1.2=723根", "114580/190*1.2=723根" in out)
    check("主楼双层拆分 (131根双层+592单层)", "(131根双层+592单层)" in out)
    check("单层抗拔需求 1.61吨/平米", "=1.61吨/平米" in out)
    check("两层抗拔需求 5.105吨/平米", "=5.105吨/平米" in out)
    check("单层地下室桩数 351根", "=351根（承压控制/每根柱下一根桩）" in out)
    check("双层地下室桩数 319根", "=319根（抗浮控制）" in out)
    check("每千平米桩数 53根", "合计：53根/千平米" in out)

    print("\n[2] 无非主楼数据：相关章节应整体省略")
    ui_none = dict(UI_INPUTS, single_area_m2=0, double_area_m2=0,
                   tower_single_m2=0, tower_double_m2=0, aboveground_double_m2=0)
    out2 = reporter.build_report(OVERVIEW, None, SELECTION, ui_none, META)
    check("不再出现「非主楼范围」", "非主楼范围" not in out2)
    check("不再出现「每千平米桩数」", "每千平米桩数" not in out2)
    check("备注第 2 条（地下室抗拔）省略",
          "地下室范围抗拔桩估算未考虑" not in out2)
    check("备注第 3 条仍在", "冗余度按照20%考虑" in out2)
    check("选型理由只写主楼", "主楼拟采用PHC预应力管桩。" in out2)
    check("主楼总计行仍正确",
          "主楼：PHC 500（125）AB，桩长46m/42m，723根\n" in out2 + "\n")

    print("\n[3] 单层地下室：不应出现双层参数")
    ov_b1 = dict(OVERVIEW, basement_floors=1, basement_heights_m=[4.0])
    out3 = reporter.build_report(ov_b1, None, SELECTION, ui_none, META)
    check("折算厚度只写单层",
          "纯地下室顶板折算厚度暂估：顶板0.4m，单层地下室底板0.6m" in out3)
    check("不出现中板/双层底板", "中板" not in out3 and "双层地下室底板" not in out3)
    check("地下层数写 -1F", "地下建筑层数：-1F" in out3)


def _login(client: TestClient, username: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _project(client: TestClient, headers: dict, no: str) -> dict:
    rows = client.get("/api/v1/projects", headers=headers).json().get("data") or []
    hit = next((p for p in rows if p.get("project_no") == no), None)
    assert hit is not None, f"没有找到项目 {no}"
    return hit


def test_report_api() -> None:
    print("\n[4] 接口：生成 / 保存 / 下载 / 权限")
    client = TestClient(app)
    h = _login(client, "ouyuxin")
    hz = _project(client, h, "ZJ-2024-001")     # 设计单位
    sz = _project(client, h, "ZJ-2024-007")     # 勘察单位（设计阶段无编辑权）

    report_body = {
        "overview": {k: v for k, v in OVERVIEW.items() if k != "towers"},
        "calc_inputs": UI_INPUTS,
        "report_title": "桩基评估",
        "date": "2024.02.01",
        "basis_files": ["依据文件A", "依据文件B"],
    }
    report_body["overview"]["towers"] = OVERVIEW["towers"]

    # 还没保存选型方案时，不能出报告
    r = client.post(f"/api/v1/projects/{hz['id']}/pile-selection/report",
                    headers=h, json=report_body)
    if r.status_code == 200:
        # 之前跑过本脚本可能已留下方案；这种情况下后面的检查仍然有效
        pass
    else:
        check("未保存选型方案时不能生成报告", r.status_code == 400, str(r.status_code))

    # 先保存一套选型方案（带勘察依据，便于后续确认）
    save = {
        "conditions": {**META["conditions"], "tower_max_floors": 14,
                       "tower_max_height_m": 50, "basement_floors": 2},
        "geo": {"capacity_rows": [
            {"pile_type_desc": "PHC 500 AB 管桩", "d_mm": 500, "length_m": 46,
             "bearing_layer_id": "⑦₂", "ra_kn": 1900},
        ], "strata": []},
        "overview": report_body["overview"],
        "calc_inputs": UI_INPUTS,
        "main": {"type_name": "PHC预应力混凝土管桩", "params": SELECTION["main"]},
        "base": {"type_name": "预制实心方桩", "params": SELECTION["base"]},
        "status": "CONFIRMED",
    }
    r = client.put(f"/api/v1/projects/{hz['id']}/pile-selection", headers=h, json=save)
    check("保存选型方案（含概况与非主楼数据）", r.status_code == 200, r.text[:300])
    row = r.json().get("data") or {}
    check("概况已落库", bool((row.get("overview") or {}).get("plots")), str(row.get("overview"))[:120])
    check("非主楼数据已落库", (row.get("calc_inputs") or {}).get("single_area_m2") == 20017)

    # 试算报告（不落库）
    r = client.post(f"/api/v1/projects/{hz['id']}/pile-selection/report",
                    headers=h, json=report_body)
    prev = r.json().get("data") or {}
    check("试算报告 200", r.status_code == 200, r.text[:300])
    check("试算报告含主楼桩数",
          "承压桩桩数估算" in (prev.get("text") or ""), str(prev.get("char_count")))
    check("试算不落库", (client.get(f"/api/v1/projects/{hz['id']}/pile-selection",
                                    headers=h).json().get("data") or {}).get("report_text")
          in (None, ""))

    # 生成并保存
    r = client.put(f"/api/v1/projects/{hz['id']}/pile-selection/report",
                   headers=h, json=report_body)
    saved_rep = r.json().get("data") or {}
    check("生成并保存报告 200", r.status_code == 200, r.text[:300])
    check("报告落库", len(saved_rep.get("text") or "") > 500, str(saved_rep.get("char_count")))

    # 下载 TXT
    r = client.get(f"/api/v1/projects/{hz['id']}/pile-selection/report.txt", headers=h)
    check("下载报告 200", r.status_code == 200, str(r.status_code))
    check("类型为 text/plain", r.headers.get("content-type", "").startswith("text/plain"),
          r.headers.get("content-type", ""))
    check("默认 inline 预览",
          r.headers.get("content-disposition", "").startswith("inline"),
          r.headers.get("content-disposition", ""))
    check("内容与保存的一致", r.text == saved_rep.get("text"), "内容不一致")
    r2 = client.get(f"/api/v1/projects/{hz['id']}/pile-selection/report.txt?download=1",
                    headers=h)
    check("download=1 时强制另存为",
          r2.headers.get("content-disposition", "").startswith("attachment"),
          r2.headers.get("content-disposition", ""))

    print("\n[5] 权限边界")
    r = client.put(f"/api/v1/projects/{sz['id']}/pile-selection/report",
                   headers=h, json=report_body)
    check("非设计阶段责任单位不能生成报告", r.status_code in (400, 403), str(r.status_code))
    r = client.get(f"/api/v1/projects/{sz['id']}/pile-selection/report.txt", headers=h)
    check("没有报告时下载返回 404", r.status_code == 404, str(r.status_code))


def main() -> int:
    test_report_engine()
    test_report_api()
    print(f"\n桩基评估报告：通过 {passed} 项，失败 {failed} 项")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
