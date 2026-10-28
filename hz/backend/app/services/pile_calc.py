"""桩数估算（纯函数，确定性）：2024 院版口径。

移植自桌面「选型」软件的 `calc.py`，公式与取整方式原样保留：

- 主楼承压桩数 = 地上重力荷载标准值总计 / 单桩抗压承载力 × 冗余度
- 单层抗拔承载力需求 = (挖深+单层底板+覆土内水头+抗浮水头)*水密度*抗浮安全系数
                        − 覆土*覆土容重*折减系数 − (顶板+底板)*砼容重
- 两层抗拔承载力需求 = (两层挖深+覆土内水头+双层底板+抗浮水头)*水密度*抗浮安全系数
                        − 覆土*覆土容重*折减系数 − (顶板+中板+底板)*砼容重
- 单层地下室桩数 = (单层投影面积−塔楼投影面积)/柱网面积 × 冗余度（承压控制，每柱一桩）
- 两层地下室桩数 = (两层投影面积−塔楼投影面积)×需求/单桩抗拔承载力 × 冗余度（抗浮控制）

**所有函数都同时返回计算中间值与公式串**，报告模板直接拿它拼"算式"，
所以这里的公式串不是注释，是**输出的一部分**，改动要连带报告一起看。
"""
from __future__ import annotations

from app.services import pile_selection_rules as R


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(v) -> str:
    """数字转规范字符串：整数不带小数点（1.2 → '1.2'，75.0 → '75'）。"""
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f == int(f) else str(f)


def _round_piles(v, mode: str | None = None) -> int:
    """桩数取整：floor / round / ceil。"""
    mode = mode or R.PILE_COUNT_ROUND
    if mode == "floor":
        return int(v)
    if mode == "ceil":
        return int(v) + (1 if v > int(v) else 0)
    return int(v + 0.5)


# ============================================================
# 主楼承压桩数
# ============================================================


def calc_main(aboveground_total_m2, capacity_t, redund_pct=None,
              aboveground_double_m2=None) -> dict:
    """主楼承压桩数。aboveground_double_m2 = 双层地下室范围内主楼地上建面（可选），
    给出后拆分为"双层 + 单层"两档桩数。"""
    redund = R.REDUND_PCT if redund_pct is None else redund_pct
    load = R.LOAD_ABOVEGROUND_T_M2
    if not capacity_t or capacity_t <= 0:
        raise ValueError("单桩抗压承载力未填写或为 0，无法估算主楼桩数")
    total_load_t = load * aboveground_total_m2
    n_total = _round_piles(total_load_t / capacity_t * (1 + redund / 100.0))
    n_double = n_single = None
    if aboveground_double_m2:
        n_double = _round_piles(
            load * aboveground_double_m2 / capacity_t * (1 + redund / 100.0),
            mode=R.SPLIT_ROUND,
        )
        n_single = n_total - n_double
    return {
        "aboveground_total_m2": aboveground_total_m2,
        "load_total_t": total_load_t,
        "n_total": n_total,
        "n_double": n_double,
        "n_single": n_single,
        "redund_pct": redund,
    }


# ============================================================
# 地下室抗拔承载力需求（吨/平米）
# ============================================================


def calc_buoyancy_single(h_m=None, cover_m=None) -> dict:
    """单层地下室抗拔承载力需求。挖深/覆土缺省取常量。"""
    h = R.BASEMENT_H_SINGLE_M if h_m is None else float(h_m)
    cover = R.COVER_BUOY_M if cover_m is None else float(cover_m)
    sb = R.SLAB_BOTTOM_SINGLE_M
    cw, head = R.COVER_WATER_BUOY_M, R.BUOY_HEAD_M
    value = (
        (h + sb + cw + head) * R.WATER_DENS_T_M3 * R.FOS_BUOYANCY
        - cover * R.COVER_DENS_T_M3 * R.COVER_REDUCE_BUOY
        - (R.SLAB_TOP_M + sb) * R.CONC_DENS_T_M3
    )
    return {
        "value": value,
        "formula": "({}+{}+{}+{})*{}-{}*{}*{}-({}+{})*{}".format(
            _fmt(h), _fmt(sb), _fmt(cw), _fmt(head), _fmt(R.FOS_BUOYANCY),
            _fmt(cover), _fmt(R.COVER_DENS_T_M3), _fmt(R.COVER_REDUCE_BUOY),
            _fmt(R.SLAB_TOP_M), _fmt(sb), _fmt(R.CONC_DENS_T_M3)),
    }


def calc_buoyancy_double(h1_m=None, h2_m=None, cover_m=None) -> dict:
    """两层地下室抗拔承载力需求。"""
    h1 = R.BASEMENT_H_SINGLE_M if h1_m is None else float(h1_m)
    h2 = R.BASEMENT_H_DOUBLE_M if h2_m is None else float(h2_m)
    cover = R.COVER_BUOY_M if cover_m is None else float(cover_m)
    sb = R.SLAB_BOTTOM_DOUBLE_M
    cw, head = R.COVER_WATER_BUOY_M, R.BUOY_HEAD_M
    value = (
        (h1 + h2 + cw + sb + head) * R.WATER_DENS_T_M3 * R.FOS_BUOYANCY
        - cover * R.COVER_DENS_T_M3 * R.COVER_REDUCE_BUOY
        - (R.SLAB_TOP_M + R.SLAB_MID_M + sb) * R.CONC_DENS_T_M3
    )
    return {
        "value": value,
        "formula": "({}+{}+{}+{}+{})*{}-{}*{}*{}-({}+{}+{})*{}".format(
            _fmt(h1), _fmt(h2), _fmt(cw), _fmt(sb), _fmt(head),
            _fmt(R.FOS_BUOYANCY), _fmt(cover), _fmt(R.COVER_DENS_T_M3),
            _fmt(R.COVER_REDUCE_BUOY), _fmt(R.SLAB_TOP_M), _fmt(R.SLAB_MID_M),
            _fmt(sb), _fmt(R.CONC_DENS_T_M3)),
    }


# ============================================================
# 纯地下室承压兼抗拔桩数
# ============================================================


def calc_base(area_single_m2, area_double_m2, tower_single_m2, tower_double_m2,
              grid_x_m, grid_y_m, buoy_double, uplift_t, redund_pct=None) -> dict:
    """非主楼桩数（向上取整）：
    - 单层：(单层投影−塔楼投影)/柱网面积×冗余（承压控制，每根柱下一根桩）
    - 双层：(双层投影−塔楼投影)×抗拔承载力需求/抗拔承载力×冗余（抗浮控制）"""
    redund = R.REDUND_PCT if redund_pct is None else redund_pct
    r = 1 + redund / 100.0
    net_single = (area_single_m2 or 0) - (tower_single_m2 or 0)
    net_double = (area_double_m2 or 0) - (tower_double_m2 or 0)
    if net_single > 0 and (grid_x_m or 0) * (grid_y_m or 0) <= 0:
        raise ValueError("柱网尺寸未填写或为 0，无法估算单层地下室桩数")
    if net_double > 0 and (not uplift_t or uplift_t <= 0):
        raise ValueError("单桩抗拔承载力未填写或为 0，无法估算双层地下室桩数")
    n_single = 0 if net_single <= 0 else _round_piles(
        net_single / (grid_x_m * grid_y_m) * r, mode=R.BASE_COUNT_ROUND)
    n_double = 0 if net_double <= 0 else _round_piles(
        net_double * buoy_double / uplift_t * r, mode=R.BASE_COUNT_ROUND)
    return {
        "area_single_m2": area_single_m2,
        "area_double_m2": area_double_m2,
        "tower_single_m2": tower_single_m2,
        "tower_double_m2": tower_double_m2,
        "grid_x_m": grid_x_m,
        "grid_y_m": grid_y_m,
        "net_single_m2": net_single,
        "net_double_m2": net_double,
        "n_single": n_single,
        "n_double": n_double,
        "n_total": n_single + n_double,
        "redund_pct": redund,
    }


# ============================================================
# 汇总
# ============================================================


def calc_summary(main: dict, base: dict, basement_proj_m2) -> dict:
    """总计与每千平米桩数。basement_proj_m2 = 单层投影 + 双层投影。"""
    if not basement_proj_m2 or basement_proj_m2 <= 0:
        raise ValueError("地下室投影面积为 0，无法估算每千平米桩数")
    n_total = main["n_total"] + base["n_total"]
    per1000 = _round_piles(n_total / basement_proj_m2 * 1000, mode=R.DENSITY_ROUND)
    return {
        "n_total": n_total,
        "basement_proj_m2": basement_proj_m2,
        "per1000": per1000,
    }
