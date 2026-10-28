"""《桩基评估》报告生成（纯规则拼接，不经过大模型）。

移植自桌面「选型」软件的 `templates.py` + `rules.py`，**输出格式逐字对齐**
（古美样例作为黄金标准，见 `scripts/test_pile_report.py`）。

设计要点：
- 用 `string.Template` 的 `${x}` 语法，避免 `mm` 之类后缀与占位符粘连；
- 所有数字先用 `_fmt()` 规范化（整数不带小数点），保证与历史报告一致；
- 非主楼数据留空时，整个"非主楼"章节与对应备注自动省略，不输出空壳。

⚠️ 这个文件的**每一行文本都是交付物的一部分**（甲方要的是可直接粘进报告的文字），
改措辞前先想清楚会不会破坏与历史报告的一致性。
"""
from __future__ import annotations

from string import Template

from app.services import pile_selection_rules as R
from app.services.pile_calc import (
    calc_base,
    calc_buoyancy_double,
    calc_buoyancy_single,
    calc_main,
    calc_summary,
)
from app.services.pile_selection import build_reason

# 分隔线（与历史报告一致的长度）
SEP_SLASH = "/" * 31
SEP_DASH = "-" * 22
SEP_DASH_LONG = "-" * 44
SEP_DASH_SHORT = "-" * 11

REPORT_TEMPLATE = Template(
    """${report_title}

${date}

${sep_slash}

${project_name}

依据文件：
${basis_files}

${sep_slash}

1. 建筑概况
${sep_dash}
${overview_section}
${sep_dash_long}

2. 桩基选型及估算假定
${sep_dash}
${selection_reason}
    主楼范围承压桩：
        承压桩：直径${d_main}mm，${main_desc}，持力层${main_layer}层${main_layer_desc}，有效长度${len_main}，抗压承载力${cap_term}${cap_main}${cap_unit_main}。
${base_assume_block}${sep_dash}
主楼承压桩按照地上建筑面积估算，重力荷载冗余度${red}%
地上重力荷载标准值暂估：${load}吨/平米
${sep_dash_long}

3. 桩基数量估算
${sep_dash}
主楼范围：
       地上重力荷载标准值总计：${load_rate}x${ag}=${load_total}吨
               地上重力荷载标准值*地上建筑面积=地上重力荷载标准值总计
       承压桩桩数估算：${load_total}/${cap_main}*${red_f}=${n_main}根${main_split}
               地上重力荷载标准值总计/单桩抗压承载力*冗余度=桩数
${base_calc_block}${sep_dash}
桩基数量总计：
${sep_dash_short}
主楼：${main_short}，桩长${len_main}，${n_main}根${main_split}
${base_total_line}${sep_dash_short}
${density_block}${sep_dash_long}

4. 总结
${sep_dash}
   主楼范围：承压桩，直径${d_main}mm，${main_desc}，持力层${main_layer}层${main_layer_desc}，有效长度${len_main}，抗压承载力${cap_term}${cap_main}${cap_unit_main}。
${summary_base_line}${sep_dash}
备注：
${remarks}
${sep_dash_long}
"""
)


# ============================================================
# 数值工具
# ============================================================


def _to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(v) -> str:
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f == int(f) else str(f)


def _fmt3(v) -> str:
    """最多三位小数（抗拔承载力需求展示，如 1.61 / 5.105）。"""
    if v is None:
        return ""
    return "{:.3f}".format(float(v)).rstrip("0").rstrip(".")


def _area_expr(area, tower) -> str:
    """面积差表达式：塔楼投影为 0 时不写 -0。"""
    return _fmt(area) if (tower or 0) <= 0 else f"({_fmt(area)}-{_fmt(tower)})"


def _first(v, default):
    return v if v is not None else default


# ============================================================
# 1. 建筑概况节
# ============================================================


def build_overview_section(overview: dict | None) -> str:
    ov = overview or {}
    lines: list[str] = []

    vr = _to_float(ov.get("volume_ratio"))
    if vr is not None:
        lines.append("容积率：{:.1f}".format(vr))

    plots = ov.get("plots") or []
    if plots:
        lines.append("规划用地面积/地上建筑面积/地下建筑面积/总建筑面积（平米）")
        if len(plots) == 1:
            p = plots[0]
            lines.append("{}/{}/{}/{}".format(
                _fmt(_to_float(p.get("land_area_m2"))),
                _fmt(_to_float(p.get("aboveground_area_m2"))),
                _fmt(_to_float(p.get("underground_area_m2"))),
                _fmt(_to_float(p.get("total_area_m2")))))
        else:
            totals = [0.0] * 4
            for p in plots:
                vals = [_to_float(p.get(k)) or 0.0 for k in
                        ("land_area_m2", "aboveground_area_m2",
                         "underground_area_m2", "total_area_m2")]
                pid = (p.get("plot_id") or "").strip()
                lines.append("{}：{}/{}/{}/{}".format(
                    pid, *[_fmt(v) for v in vals]))
                totals = [t + v for t, v in zip(totals, vals)]
            lines.append("总计：{}/{}/{}/{}".format(*[_fmt(t) for t in totals]))

    if _to_float(ov.get("tower_count")) is not None:
        lines.append("住宅单体数量：{}".format(_fmt(ov.get("tower_count"))))

    towers = ov.get("towers") or []
    if towers:
        floors = sorted({int(f) for f in
                         (_to_float(t.get("floors")) for t in towers) if f})
        seg = "、".join("{}F".format(f) for f in floors)
        hr = (ov.get("height_range") or "").strip()
        if hr:
            seg += "，高度{}".format(hr)
        lines.append("地上建筑层数：{}".format(seg))

    if _to_float(ov.get("height_limit_m")) is not None:
        lines.append("建筑限高：{}m".format(_fmt(ov.get("height_limit_m"))))

    bf = _to_float(ov.get("basement_floors"))
    if bf is not None:
        heights = [_to_float(h) for h in (ov.get("basement_heights_m") or [])]
        heights = [h for h in heights if h is not None]
        if not heights:
            heights = [R.BASEMENT_H_SINGLE_M] * int(bf)
        if len(set(heights)) == 1:
            h_str = "暂估层高{}m".format(_fmt(heights[0]))
        else:
            h_str = "{}m+{}m".format(_fmt(heights[0]), _fmt(heights[-1]))
        lines.append("地下建筑层数：-{}F（{}）".format(int(bf), h_str))

    cover = _to_float(ov.get("cover_thick_m"))
    diff = _to_float(ov.get("indoor_outdoor_diff_m"))
    if cover is not None or diff is not None:
        seg = "纯地下室顶板覆土厚度暂估{}m".format(_fmt(_first(cover, R.COVER_BUOY_M)))
        if diff is not None:
            seg += "，室内外高差暂估{}m".format(_fmt(diff))
        lines.append(seg)

    st_ = _first(_to_float(ov.get("slab_top_m")), R.SLAB_TOP_M)
    sm_ = _first(_to_float(ov.get("slab_mid_m")), R.SLAB_MID_M)
    sbs = _first(_to_float(ov.get("slab_bottom_single_m")), R.SLAB_BOTTOM_SINGLE_M)
    sbd = _first(_to_float(ov.get("slab_bottom_double_m")), R.SLAB_BOTTOM_DOUBLE_M)
    if any(k in ov for k in ("slab_top_m", "slab_mid_m", "slab_bottom_m",
                             "slab_bottom_single_m", "slab_bottom_double_m")) \
            or st_ is not None:
        if bf is not None and int(bf) < 2:
            # 单层地下室：无中板、无双层底板（均为双层地下室参数）
            lines.append(
                "纯地下室顶板折算厚度暂估：顶板{}m，单层地下室底板{}m".format(
                    _fmt(st_), _fmt(sbs)))
        else:
            lines.append(
                "纯地下室顶板折算厚度暂估：顶板{}m，中板{}m，单层地下室底板{}m，双层地下室底板{}m".format(
                    _fmt(st_), _fmt(sm_), _fmt(sbs), _fmt(sbd)))

    return "\n".join(lines)


# ============================================================
# 勘察复核注记
# ============================================================


def _geo_notes(geo, m, b) -> list[str]:
    """勘察参数与选型假定的复核注记（返回无编号条文）。

    原软件里这些注记用于提示"AI 提取 vs 典型假定"的差异；
    本平台只支持手工录入勘察表，所以只在
    「有勘察数据但承载力表为空」「fs/fp 超范围」这些能判断的情况下出注记。
    """
    if not geo:
        return []
    notes: list[str] = []
    if not (geo.get("capacity_rows") or []):
        notes.append(
            "勘察报告承载力表未能自动解析（本平台仅支持手工录入），"
            "以上桩径/桩长/承载力为典型假定值，请对照勘察报告人工复核。")
    fs = fp = None
    strata = geo.get("strata") or []
    layer = None
    if m.get("layer"):
        layer = next((s for s in strata if s.get("layer_id") == m["layer"]), None)
    if layer is not None:
        fs, fp = _to_float(layer.get("fs_kpa")), _to_float(layer.get("fp_kpa"))
    if fs is not None and fp is not None:
        notes.append(
            "勘察报告{}层桩基设计参数：钻孔灌注桩极限侧阻力 fs={}kPa、"
            "极限端阻力 fp={}kPa（依据勘察报告桩基设计参数表）。".format(
                m.get("layer") or "", _fmt(fs), _fmt(fp)))
    if geo.get("pile_recommendation"):
        notes.append("勘察报告桩基建议摘录：{}".format(geo["pile_recommendation"]))
    if not notes:
        return []
    warn = []
    if fs is not None and not (R.FS_RANGE[0] <= fs <= R.FS_RANGE[1]):
        warn.append("fs")
    if fp is not None and not (R.FP_RANGE[0] <= fp <= R.FP_RANGE[1]):
        warn.append("fp")
    if warn:
        notes.append(
            "注：勘察报告{}层{}与初步假定取值依据存在差异，请复核单桩承载力。".format(
                m.get("layer") or "", "、".join(warn)))
    return notes


# ============================================================
# 主入口
# ============================================================


def build_report(overview: dict | None, geo: dict | None,
                 selection: dict, ui_inputs: dict, meta: dict) -> str:
    """生成完整评估报告文本。

    selection: {"main": {type_name, desc, short, d_mm, lengths, capacity_t,
                          layer, layer_desc},
                "base": {type_name, desc, short, d_mm, lengths, uplift_t,
                          layer, layer_desc}}
    ui_inputs: 非主楼数据 —— single_area_m2 / double_area_m2 /
               tower_single_m2 / tower_double_m2 / grid_x_m / grid_y_m /
               aboveground_double_m2
    meta:      date / basis_files(list) / project_name / conditions
    """
    m = selection["main"]
    b = selection["base"]
    ui = ui_inputs or {}
    conditions = meta.get("conditions") or {}

    # ---- 桩数计算 ----
    ag_total = 0.0
    for p in (overview or {}).get("plots") or []:
        ag_total += _to_float(p.get("aboveground_area_m2")) or 0.0
    main = calc_main(ag_total, m.get("capacity_t"),
                     aboveground_double_m2=_to_float(ui.get("aboveground_double_m2")))

    # 挖深 = 概况地下室暂估层高，覆土 = 概况覆土厚度（缺省用常量）
    ov_b = overview or {}
    bf_ov = _to_float(ov_b.get("basement_floors"))
    hts = [_to_float(h) for h in (ov_b.get("basement_heights_m") or [])]
    hts = [h for h in hts if h is not None]
    if not hts:
        hts = [R.BASEMENT_H_SINGLE_M] * (int(bf_ov) if bf_ov is not None else 1)
    cover_ov = _to_float(ov_b.get("cover_thick_m"))
    cover = R.COVER_BUOY_M if cover_ov is None else cover_ov
    buoy1 = calc_buoyancy_single(hts[0], cover)
    buoy2 = calc_buoyancy_double(hts[0], hts[-1], cover)

    area_s = _first(_to_float(ui.get("single_area_m2")), 0.0)
    area_d = _first(_to_float(ui.get("double_area_m2")), 0.0)
    has_single = area_s > 0
    has_double = area_d > 0
    has_base = has_single or has_double
    t_s = _first(_to_float(ui.get("tower_single_m2")), 0.0)
    t_d = _first(_to_float(ui.get("tower_double_m2")), 0.0)
    gx = _first(_to_float(ui.get("grid_x_m")), R.GRID_X_M)
    gy = _first(_to_float(ui.get("grid_y_m")), R.GRID_Y_M)
    base = calc_base(area_s, area_d, t_s, t_d, gx, gy, buoy2["value"], b.get("uplift_t"))
    summary = calc_summary(main, base, area_s + area_d) if has_base else None

    # ---- 选型理由段（无非主楼数据时只写主楼选型）----
    reason = build_reason(conditions, m.get("type_name"),
                          b.get("type_name") if has_base else None)

    # ---- 依据文件（自动补编号）----
    basis_lines: list[str] = []
    for i, raw in enumerate(meta.get("basis_files") or [], 1):
        line = str(raw).strip()
        line = line[len(str(i)) + 1:] if line.startswith(f"{i}. ") or \
            line.startswith(f"{i}.") else line
        if line:
            basis_lines.append(f"{i}.{line}")
    if not basis_lines:
        basis_lines = ["1.（请填写依据文件）", "2.（请填写依据文件）", "3.（请填写依据文件）"]

    # ---- 主楼双层/单层拆分显示 ----
    if main["n_double"] is not None:
        split = f"({main['n_double']}根双层+{main['n_single']}单层)"
    else:
        split = ""

    red_f = _fmt(1 + R.REDUND_PCT / 100.0)
    remark_items = list(R.REMARK_ITEMS)
    if not has_base:
        remark_items.pop(1)  # 第 2 条为地下室抗拔桩备注，无非主楼数据时省略
    remarks = "\n".join(
        "{}. {}".format(i + 1, s.format(red=R.REDUND_PCT))
        for i, s in enumerate(remark_items)
    )

    # ---- 勘察复核注记（追加在备注之后，编号顺延）----
    geo_notes = _geo_notes(geo, m, b)
    if geo_notes:
        start = len(remark_items) + 1
        remarks += "\n" + "\n".join(
            "{}. {}".format(start + i, s) for i, s in enumerate(geo_notes))

    # ---- 非主楼相关块（留空时整体省略）----
    if has_base:
        fml_n1 = "{}/({}*{})*{}".format(
            _area_expr(base["area_single_m2"], base["tower_single_m2"]),
            _fmt(base["grid_x_m"]), _fmt(base["grid_y_m"]), red_f)
        fml_n2 = "{}*{}/{}*{}".format(
            _area_expr(base["area_double_m2"], base["tower_double_m2"]),
            _fmt3(buoy2["value"]), _fmt(b.get("uplift_t")), red_f)
        calc_lines = [SEP_DASH_LONG, "非主楼范围：", "    抗浮工况："]
        if has_single:
            calc_lines += [
                "        单层地下室抗拔承载力需求：{}={}吨/平米".format(
                    buoy1["formula"], _fmt3(buoy1["value"])),
                "            (地下室挖深+覆土厚度内水头高)*水密度*抗浮安全系数-"
                "覆土重-(地下室投影单方砼厚度)*砼容重=单方水浮力",
            ]
        if has_double:
            calc_lines += [
                "        两层地下室抗拔承载力需求：{}={}吨/平米".format(
                    buoy2["formula"], _fmt3(buoy2["value"])),
                "            (地下室挖深+覆土厚度内水头高)*水密度*抗浮安全系数-"
                "覆土重-(地下室投影单方砼厚度)*砼容重=单方水浮力",
            ]
        calc_lines.append("    承压兼抗拔桩桩数估算：")
        if has_single:
            calc_lines += [
                "        单层地下室：{}={}根（承压控制/每根柱下一根桩）".format(
                    fml_n1, base["n_single"]),
                "            (单层地下室投影面积-塔楼投影面积)/柱网尺寸*冗余度=桩数",
            ]
        if has_double:
            calc_lines += [
                "        双层地下室：{}={}根（抗浮控制）".format(fml_n2, base["n_double"]),
                "            (地下室投影面积-塔楼投影面积)*单方抗拔承载力需求/"
                "单桩抗拔承载力*冗余度=桩数",
            ]
        base_calc_block = "\n".join(calc_lines) + "\n"

        base_assume_block = ("    地下室范围承压兼抗拔桩：\n"
                             "        {}，持力层{}层{}，有效长度{}，"
                             "抗拔承载力{}{}{}。\n").format(
            b.get("desc") or "", b.get("layer") or "", b.get("layer_desc") or "",
            b.get("lengths") or "", R.CAP_TERM, _fmt(b.get("uplift_t")),
            R.CAP_UNIT_BASE)

        total_parts = []
        if has_single:
            total_parts.append("{}根单层".format(base["n_single"]))
        if has_double:
            total_parts.append("{}双层".format(base["n_double"]))
        base_total_line = "非主楼：{}，有效长度{}，总桩数{}根{}\n".format(
            b.get("short") or b.get("desc") or "", b.get("lengths") or "",
            base["n_total"], "(" + "+".join(total_parts) + ")")

        density_block = ("每千平米桩数：总桩数（{}根）/地下室投影面积（{}m2）\n"
                         "合计：{}根/千平米\n").format(
            summary["n_total"], _fmt(summary["basement_proj_m2"]),
            summary["per1000"])

        summary_base_line = (
            "   地下室范围：承压兼抗拔桩，{}，持力层{}层{}，有效长度{}，"
            "抗拔承载力{}{}{}。\n").format(
            b.get("desc") or "", b.get("layer") or "", b.get("layer_desc") or "",
            b.get("lengths") or "", R.CAP_TERM, _fmt(b.get("uplift_t")),
            R.CAP_UNIT_BASE)
    else:
        base_calc_block = ""
        base_assume_block = ""
        base_total_line = ""
        density_block = ""
        summary_base_line = ""

    slots = {
        # 标题可覆盖（原软件把甲方名写死在标题里：中海前期地块桩基评估）
        "report_title": (meta.get("report_title") or "桩基评估").strip(),
        "date": meta.get("date") or "",
        "project_name": meta.get("project_name")
        or (overview or {}).get("project_name") or "（项目名称）",
        "basis_files": "\n".join(basis_lines),
        "sep_slash": SEP_SLASH,
        "sep_dash": SEP_DASH,
        "sep_dash_long": SEP_DASH_LONG,
        "sep_dash_short": SEP_DASH_SHORT,
        "overview_section": build_overview_section(overview),
        "selection_reason": reason,
        "d_main": _fmt(m.get("d_mm")),
        "main_desc": m.get("desc") or "",
        "main_layer": m.get("layer") or "",
        "main_layer_desc": m.get("layer_desc") or "",
        "len_main": m.get("lengths") or "",
        "cap_main": _fmt(m.get("capacity_t")),
        "cap_term": R.CAP_TERM,
        "cap_unit_main": R.CAP_UNIT_MAIN,
        "base_assume_block": base_assume_block,
        "red": R.REDUND_PCT,
        "red_f": red_f,
        "load": _fmt(R.LOAD_ABOVEGROUND_T_M2),
        "load_rate": _fmt(R.LOAD_ABOVEGROUND_T_M2),
        "ag": _fmt(main["aboveground_total_m2"]),
        "load_total": _fmt(main["load_total_t"]),
        "n_main": main["n_total"],
        "main_split": split,
        "base_calc_block": base_calc_block,
        "main_short": m.get("short") or m.get("desc") or "",
        "base_total_line": base_total_line,
        "density_block": density_block,
        "summary_base_line": summary_base_line,
        "remarks": remarks,
    }
    return REPORT_TEMPLATE.substitute(slots)
