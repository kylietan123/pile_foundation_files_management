"""桩基选型引擎（纯规则、确定性）：项目条件 + 勘察参数 → 桩型建议 + 桩参数建议。

来源：桌面「选型」软件（`选型/platform/pile_selection.py`），算法与标定原样沿用：

- 受限场景（地铁保护区/内环内/临近高架/密集建筑群）：挤土桩硬性排除，非挤土桩胜出；
- 经济场景（无上述限制）：成本/工期主导，PHC 等挤土桩胜出；
- 桩径按院版《桩基方案》第五、六章选型图定，勘察表有对应直径行直接用行值，
  没有则用其他直径行线插法取承载力，两者都没有才回落典型组合。

**所有建议仅作参考**，最终以设计人在界面上的确认为准（确认结果存库留痕）。
本模块不依赖大模型、不读文件、不联网，可单测。
"""
from __future__ import annotations

from app.services import pile_selection_rules as R

ROLE_MAIN = "main"        # 主楼承压
ROLE_BASE = "base"        # 纯地下室承压兼抗拔

#: 桩型名关键词（用于在勘察承载力表行的桩型描述中匹配）
_TYPE_KEYWORDS: dict[str, list[str]] = {
    "钻孔灌注桩(端注浆)": ["灌注", "钻孔"],
    "钻孔灌注桩": ["灌注", "钻孔"],
    "PHC预应力混凝土管桩": ["PHC", "管桩"],
    "UHC高性能管桩": ["UHC"],
    "PHS预应力混凝土空心方桩": ["PHS", "空心方桩"],
    "预制实心方桩": ["方桩"],
    "根植桩": ["根植"],
}


# ============================================================
# 一、硬性排除与权重
# ============================================================


def has_restriction(conditions: dict) -> bool:
    """是否存在必须用非挤土桩的硬性限制。"""
    return bool(
        conditions.get("metro_protection_zone")
        or conditions.get("inner_ring")
        or conditions.get("near_viaduct_bridge")
        or conditions.get("dense_buildings_nearby")
    )


def restriction_reasons(conditions: dict) -> list[str]:
    """把限制条件翻成中文，用于报错与理由段落。"""
    reasons: list[str] = []
    if conditions.get("inner_ring"):
        reasons.append("内环内")
    if conditions.get("metro_protection_zone"):
        reasons.append("地铁保护区")
    if conditions.get("near_viaduct_bridge"):
        reasons.append("临近高架/桥梁")
    if conditions.get("dense_buildings_nearby"):
        reasons.append("密集建筑群")
    return reasons


def hard_filter(role: str, conditions: dict) -> dict[str, str]:
    """硬性排除规则。返回 {桩型名: 排除原因}。"""
    excluded: dict[str, str] = {}
    if has_restriction(conditions):
        joined = "、".join(restriction_reasons(conditions))
        for p in R.DISPLACEMENT_PILES:
            excluded[p] = f"位于{joined}，必须选用非挤土桩"
    if role == ROLE_BASE:
        excluded["根植桩"] = "非塔楼区域用于抗拔桩经济性不明显"
    if conditions.get("need_permanent_temp_combo"):
        for p in R.DISPLACEMENT_PILES:
            excluded.setdefault(p, "上海暂无预制桩做立柱桩案例")
        excluded.setdefault("根植桩", "上海暂无根植桩做立柱桩案例")
    return excluded


def _weights(role: str, conditions: dict) -> dict[str, float]:
    """按场景选权重，再叠加条件系数。"""
    if has_restriction(conditions):
        w = dict(R.WEIGHTS_RESTRICTED)
        if (
            conditions.get("metro_protection_zone")
            or conditions.get("inner_ring")
            or conditions.get("near_viaduct_bridge")
        ):
            w["挤土效应"] *= 3.0
            w["施工噪声"] *= 1.5
        if conditions.get("dense_buildings_nearby"):
            w["挤土效应"] *= 2.0
    else:
        w = dict(R.WEIGHTS_ECONOMY)
    if conditions.get("tight_budget"):
        w["工程成本"] *= 2.0
    if conditions.get("tight_schedule"):
        w["施工工期"] *= 2.0
    if conditions.get("noise_sensitive"):
        w["施工噪声"] *= 2.5
    if conditions.get("env_protection_strict"):
        w["挤土效应"] *= 1.5
        w["施工噪声"] *= 1.5
    if role == ROLE_MAIN:
        w["承载力"] *= 1.5
    else:
        w["承载力"] *= 0.7
        w["挤土效应"] *= 1.3
    if conditions.get("need_permanent_temp_combo"):
        w["技术成熟度"] *= 2.0
        w["适用性匹配"] *= 1.5
    if conditions.get("has_inner_support"):
        w["技术成熟度"] *= 1.5
    return w


def _adjust_scores(role: str, conditions: dict, name: str, scores: dict) -> dict:
    """按项目条件微调单项评分。"""
    adjusted = dict(scores)
    if role == ROLE_MAIN and name == "钻孔灌注桩(端注浆)":
        adjusted["适用性匹配"] = min(5, adjusted["适用性匹配"] + 1)
        adjusted["承载力"] = min(5, adjusted["承载力"] + 1)
    if role == ROLE_BASE and name == "钻孔灌注桩":
        adjusted["适用性匹配"] = min(5, adjusted["适用性匹配"] + 1)
    if role == ROLE_MAIN and name == "钻孔灌注桩":
        adjusted["适用性匹配"] = max(1, adjusted["适用性匹配"] - 1)
    if role == ROLE_BASE and name in ("PHS预应力混凝土空心方桩", "预制实心方桩"):
        adjusted["适用性匹配"] = min(5, adjusted["适用性匹配"] + 1)
    if conditions.get("noise_sensitive") and scores["施工噪声"] <= 2:
        adjusted["施工噪声"] = max(1, adjusted["施工噪声"] - 1)
    if conditions.get("tight_schedule") and scores["施工工期"] <= 2:
        adjusted["施工工期"] = max(1, adjusted["施工工期"] - 1)
    return adjusted


def rank_piles(role: str, conditions: dict) -> list[dict]:
    """评分排序，返回 [{name, label, category, total, hard_excluded, not_considered, reason}]。

    三级排序：硬性排除/暂不考虑垫底 → 优选桩型（PHC、端注浆）靠前 → 总分降序。
    """
    weights = _weights(role, conditions)
    excluded = hard_filter(role, conditions)
    ranked: list[dict] = []
    for name, k in R.PILE_KNOWLEDGE.items():
        base = {
            "name": name,
            "label": k.get("label", name),
            "category": k.get("category", ""),
            "applicability": k.get("applicability", ""),
        }
        if name in R.SELECTION_NOT_CONSIDERED:
            if name in excluded:
                ranked.append({**base, "total": -999.0, "hard_excluded": True,
                               "reason": excluded[name], "not_considered": False})
            else:
                ranked.append({**base, "total": -999.5, "hard_excluded": False,
                               "reason": "选型阶段暂不考虑该桩型（可人工选择）",
                               "not_considered": True})
            continue
        adjusted = _adjust_scores(role, conditions, name, k["scores"])
        total = sum(adjusted[d] * weights[d] for d in R.SCORE_DIMENSIONS)
        if name in excluded:
            ranked.append({**base, "total": -999.0, "hard_excluded": True,
                           "reason": excluded[name], "not_considered": False})
        else:
            ranked.append({**base, "total": round(total, 2), "hard_excluded": False,
                           "reason": "", "not_considered": False})
    ranked.sort(
        key=lambda x: (
            0 if not x["hard_excluded"] and not x["not_considered"] else 1,
            0 if x["name"] in R.PREFERRED_PILES else 1,
            -x["total"],
        )
    )
    return ranked


# ============================================================
# 二、桩径规则（高度带 + 地下层数 + 线插法）
# ============================================================


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _combos_key(role: str, conditions: dict) -> str:
    if role == ROLE_MAIN:
        return "main"
    floors = conditions.get("basement_floors") or 2
    return "base_B2" if floors >= 2 else "base_B1"


def height_band(conditions: dict) -> int | None:
    """主楼高度带：0=低多层、1=中高层、2=高层、3=超高层。

    层数与高度都无法判断时返回 None（桩径规则不生效，沿用勘察表行匹配）。
    """
    h = _to_float(conditions.get("tower_max_height_m"))
    if h is not None and h > 100:
        return R.BAND_SUPERHIGH
    f = _to_float(conditions.get("tower_max_floors"))
    if f is None:
        return None
    f = int(f)
    if f <= 6:
        return R.BAND_LOWRISE
    if f <= 9:
        return R.BAND_MIDRISE
    if h is None:
        h = f * 3.0   # 层高缺省按 3m 估
    return R.BAND_SUPERHIGH if h > 100 else R.BAND_HIGHRISE


def rule_diameter(type_name: str, role: str, conditions: dict) -> int | None:
    """按院版选型图确定桩径（mm）。桩型或高度带规则未覆盖时返回 None。"""
    tables = R.DIAMETER_RULES.get(role)
    if not tables:
        return None
    if role == ROLE_MAIN:
        band = height_band(conditions)
        if band is None:
            return None
        if has_restriction(conditions):
            entry = (tables.get("restricted") or {}).get(type_name)
            if not entry:
                return None
            if conditions.get("metro_protection_zone"):
                return entry["metros"][band]
            return entry["base"][band]
        lst = (tables.get("economy") or {}).get(type_name)
        return lst[band] if lst else None
    floors = conditions.get("basement_floors") or 2
    key = "B3" if floors >= 3 else ("B2" if floors >= 2 else "B1")
    per = tables.get(type_name)
    return per.get(key) if per else None


def _report_d_ok(type_name: str, d) -> bool:
    """AI/人工录入的报告桩径是否可信（非标值宁回落也不采用）。"""
    if d is None:
        return False
    d = int(round(d))
    allowed = R.REPORT_D_CAST if type_name in R.CAST_TYPES else R.REPORT_D_PREFAB
    return d in allowed


def _interp(points: list[tuple[float, float]], target: float):
    """线插法：≥2 点用夹逼两点线性插值（范围外用最近两点线性外延）；
    单点按直径比例折算；空返回 None。"""
    pts = sorted(points)
    if not pts:
        return None
    if len(pts) == 1:
        d, v = pts[0]
        return v * target / d if d else None
    below = [p for p in pts if p[0] <= target]
    above = [p for p in pts if p[0] >= target]
    if below and above:
        d1, v1 = max(below)
        d2, v2 = min(above)
    else:
        d1, v1 = pts[0]
        d2, v2 = pts[1]
    if d2 == d1:
        return v1
    return v1 + (v2 - v1) * (target - d1) / (d2 - d1)


def _label_refresh(type_name: str, role: str, params: dict, d_mm, combo: dict) -> None:
    """桩径与典型组合不一致时按新桩径重生成短名/描述，保证两处口径一致。"""
    cd = _to_float(combo.get("d_mm"))
    if cd is None or int(cd) == int(d_mm):
        return
    tpl = R.PILE_LABEL_BY_TYPE.get(type_name)
    if not tpl:
        return
    d = int(d_mm)
    wall = (tpl.get("wall") or {}).get(d)
    if tpl.get("wall") and wall is None:
        return  # 该直径壁厚未收录：保守不改标签
    fmt = {"d": d, "t": wall}
    params["short"] = tpl["short"].format(**fmt)
    params["desc"] = (tpl["desc"] if role == ROLE_MAIN else tpl["base_desc"]).format(**fmt)


def _row_matches_type(row: dict, type_name: str) -> bool:
    desc = str(row.get("pile_type_desc") or "") + str(row.get("note") or "")
    if type_name in ("钻孔灌注桩(端注浆)", "钻孔灌注桩"):
        return ("灌注" in desc or "钻孔桩" in desc) and not any(
            k in desc for k in ("PHC", "UHC", "PHS", "方桩", "根植")
        )
    keywords = _TYPE_KEYWORDS.get(type_name, [])
    return any(k in desc for k in keywords)


def _layer_desc_of(geo: dict, layer_id: str | None) -> str | None:
    if not layer_id:
        return None
    for s in geo.get("strata") or []:
        if s.get("layer_id") == layer_id and s.get("name"):
            return s["name"]
    return None


def pick_params(type_name: str, role: str, conditions: dict, geo: dict | None) -> dict:
    """为选定桩型确定桩参数。

    优先级：规则桩径有对应勘察表行 → 用行值；
    无对应行 → 其他直径行线插法取承载力；再不行 → 有勘察报告则用报告提取值；
    最后 → 典型组合兜底。

    返回 {desc, short, d_mm, lengths, capacity_t/uplift_t, layer, layer_desc,
         from_row, from_interp, note}
    """
    key = _combos_key(role, conditions)
    combo = (R.PILE_COMBOS.get(type_name, {}) or {}).get(key) or {}
    params: dict = dict(combo)

    rows: list[dict] = []
    if geo:
        rows = [r for r in (geo.get("capacity_rows") or []) if _row_matches_type(r, type_name)]

    if rows:
        def _rv(r: dict) -> float:
            return _to_float(r.get("rd_kn")) or _to_float(r.get("ra_kn")) or 0

        rule_d = rule_diameter(type_name, role, conditions)
        candidates = (
            rows if rule_d is None
            else [r for r in rows if int(_to_float(r.get("d_mm")) or 0) == rule_d]
        )
        if role == ROLE_MAIN:
            # 主楼：取承载力最大、桩长更长的组合（持力层深）
            candidates.sort(key=lambda r: (_rv(r), _to_float(r.get("length_m")) or 0))
            row = candidates[-1] if candidates else None
        else:
            # 地下室：取桩长较短、承载力够用的组合
            candidates.sort(key=lambda r: (_to_float(r.get("length_m")) or 999, -_rv(r)))
            row = candidates[0] if candidates else None

        if row is not None:
            d = _to_float(row.get("d_mm"))
            ln = _to_float(row.get("length_m"))
            rd = _to_float(row.get("rd_kn"))
            rtd = _to_float(row.get("rtd_kn"))
            ra_kn = _to_float(row.get("ra_kn"))
            if d and ln and (rd or rtd or ra_kn):
                if role == ROLE_MAIN:
                    if rd:
                        # 表中直接给出抗压设计值：直接采用，不再叠加后注浆系数
                        params["capacity_t"] = round(rd / 10, 0) or combo.get("capacity_t")
                    else:
                        if type_name == "钻孔灌注桩(端注浆)":
                            ra_kn = (ra_kn or 0) * 1.72
                        params["capacity_t"] = round((ra_kn or 0) / 10, 0) or combo.get("capacity_t")
                else:
                    if rtd:
                        params["uplift_t"] = round(rtd / 10, 0) or combo.get("uplift_t")
                    else:
                        # 无抗拔列：按特征值一半估（历史口径 Φ600/35m ≈ 100t）
                        params["uplift_t"] = round((ra_kn or 0) / 20, 0) or combo.get("uplift_t")
                params["d_mm"] = int(d)
                _label_refresh(type_name, role, params, d, combo)
                params["lengths"] = f"{int(round(ln))}m"
                if row.get("bearing_layer_id"):
                    params["layer"] = row["bearing_layer_id"]
                    ld = _layer_desc_of(geo, row["bearing_layer_id"])
                    if ld:
                        params["layer_desc"] = ld
                params["from_row"] = True
                return params

        # 规则桩径在表中无对应行 → 用其他直径行线插法取值
        if rule_d is not None:
            pts: dict[str, list] = {"rd": [], "rtd": [], "ra": []}
            for r in rows:
                d = _to_float(r.get("d_mm"))
                if not d:
                    continue
                rd = _to_float(r.get("rd_kn"))
                rtd = _to_float(r.get("rtd_kn"))
                ra_kn = _to_float(r.get("ra_kn"))
                if rd:
                    pts["rd"].append((d, rd))
                if rtd:
                    pts["rtd"].append((d, rtd))
                if ra_kn:
                    pts["ra"].append((d, ra_kn))
            col = ("rd" if pts["rd"] else "ra") if role == ROLE_MAIN else (
                "rtd" if pts["rtd"] else "ra")
            v = _interp(pts[col], rule_d)
            if v is not None:
                if role == ROLE_MAIN:
                    if col == "rd":
                        params["capacity_t"] = round(v / 10, 0) or combo.get("capacity_t")
                    else:
                        if type_name == "钻孔灌注桩(端注浆)":
                            v *= 1.72
                        params["capacity_t"] = round(v / 10, 0) or combo.get("capacity_t")
                else:
                    if col == "rtd":
                        params["uplift_t"] = round(v / 10, 0) or combo.get("uplift_t")
                    else:
                        params["uplift_t"] = round(v / 20, 0) or combo.get("uplift_t")
                params["d_mm"] = rule_d
                _label_refresh(type_name, role, params, rule_d, combo)
                # 桩长/持力层取直径最接近规则桩径的行（不插值；距离相同取大直径，偏保守）
                ref = min(
                    rows,
                    key=lambda r: (
                        abs((_to_float(r.get("d_mm")) or 0) - rule_d),
                        -(_to_float(r.get("d_mm")) or 0),
                    ),
                )
                ln = _to_float(ref.get("length_m"))
                if ln:
                    params["lengths"] = f"{int(round(ln))}m"
                if ref.get("bearing_layer_id"):
                    params["layer"] = ref["bearing_layer_id"]
                    ld = _layer_desc_of(geo, ref["bearing_layer_id"])
                    if ld:
                        params["layer_desc"] = ld
                params["from_row"] = True
                params["from_interp"] = True
                params["note"] = (
                    f"桩径按第五/六章选型图取{rule_d}mm，"
                    f"承载力按勘察表其他直径线插法取值，请复核"
                )
                return params

    # 无可用勘察表行但有勘察数据：用报告提取值（可信桩径优先），不再硬套样例地层
    if geo and not rows:
        lp = ((geo.get("llm_params") or {}).get("main" if role == ROLE_MAIN else "base")) or {}
        lp_d = _to_float(lp.get("d_mm"))
        d = int(round(lp_d)) if _report_d_ok(type_name, lp_d) else None
        if d is None:
            d = rule_diameter(type_name, role, conditions)
        if d is not None:
            params["d_mm"] = d
            _label_refresh(type_name, role, params, d, combo)
        lmin = _to_float(lp.get("length_min_m"))
        lmax = _to_float(lp.get("length_max_m"))
        if lmin:
            if lmax and lmax != lmin:
                params["lengths"] = f"{int(round(lmin))}m/{int(round(lmax))}m"
            else:
                params["lengths"] = f"{int(round(lmin))}m"
        if role == ROLE_MAIN:
            ct = _to_float(lp.get("capacity_t"))
            if ct:
                params["capacity_t"] = round(ct)
        else:
            ut = _to_float(lp.get("uplift_t"))
            if ut:
                params["uplift_t"] = round(ut)
        bid = str(lp.get("bearing_layer_id") or "").strip() or geo.get("bearing_layer_id")
        if not bid:
            bs = [x for x in (geo.get("strata") or []) if x.get("is_bearing")]
            if bs:
                bid = bs[0].get("layer_id")
        if bid:
            params["layer"] = bid
            ld = str(lp.get("layer_desc") or "").strip() or (_layer_desc_of(geo, bid) or "")
            params["layer_desc"] = ld or "按勘察报告确定"
        else:
            params["layer"] = ""
            params["layer_desc"] = "按勘察报告确定"

    params["from_row"] = False
    return params


# ============================================================
# 三、主入口
# ============================================================


def _top_of(ranking: list[dict]) -> dict:
    return next(
        (r for r in ranking if not r["hard_excluded"] and not r.get("not_considered")),
        ranking[0],
    )


def suggest(conditions: dict, geo: dict | None) -> dict:
    """给出主楼 / 地下室桩型建议。

    返回 {main: {type_name, label, ranking, excluded, params, diameter_rule},
          base: {...}, scenario, restrictions, height_band, basis}
    """
    main_ranking = rank_piles(ROLE_MAIN, conditions)
    base_ranking = rank_piles(ROLE_BASE, conditions)
    main_top = _top_of(main_ranking)
    base_top = _top_of(base_ranking)

    def _pack(role: str, ranking: list[dict], top: dict) -> dict:
        return {
            "role": role,
            "type_name": top["name"],
            "label": top["label"],
            "ranking": ranking,
            "excluded": [r for r in ranking if r["hard_excluded"]],
            "params": pick_params(top["name"], role, conditions, geo),
            "diameter_rule": rule_diameter(top["name"], role, conditions),
        }

    main_pack = _pack(ROLE_MAIN, main_ranking, main_top)
    base_pack = _pack(ROLE_BASE, base_ranking, base_top)

    #: 依据来源 —— survey=至少一侧匹配到勘察承载力表行；
    #: typical=只有典型组合（历史项目经验值），不能作为设计依据。
    basis = "survey" if (
        main_pack["params"].get("from_row") or base_pack["params"].get("from_row")
    ) else "typical"

    return {
        "main": main_pack,
        "base": base_pack,
        "scenario": "restricted" if has_restriction(conditions) else "economy",
        "restrictions": restriction_reasons(conditions),
        "height_band": height_band(conditions),
        "basis": basis,
    }


def build_reason(conditions: dict, main_type: str, base_type: str | None = None) -> str:
    """选型理由段（报告第 2 节开头）。base_type 为 None 时只写主楼选型。"""
    m_label = R.PILE_KNOWLEDGE.get(main_type, {}).get("label", main_type)
    if base_type is None:
        tail = f"主楼拟采用{m_label}。"
    else:
        b_label = R.PILE_KNOWLEDGE.get(base_type, {}).get("label", base_type)
        tail = f"主楼拟采用{m_label}，纯地下室拟采用{b_label}。"
    if has_restriction(conditions):
        reasons = []
        if conditions.get("metro_protection_zone"):
            reasons.append("地铁50m安全保护区范围内")
        if conditions.get("inner_ring"):
            reasons.append("内环内")
        if conditions.get("near_viaduct_bridge"):
            reasons.append("临近高架/桥梁")
        if conditions.get("dense_buildings_nearby"):
            reasons.append("周边建筑密集")
        return (
            "根据图纸中提供的项目定位，项目地块位于{}，"
            "为避免挤土效应对周边环境的不利影响，{}".format("、".join(reasons), tail)
        )
    return "根据图纸中提供的项目定位，项目地块不在地铁50m安全保护区范围内，{}".format(tail)


def pile_type_options(with_combos: bool = False) -> list[dict]:
    """校对表下拉用：全部桩型（含"暂不考虑"的，供人工选择）。

    with_combos=True 时附带典型桩参数组合，前端切换桩型即可就地重填参数，
    不必再调一次接口（典型参数以后端知识库为唯一来源）。
    """
    out = []
    for name, k in R.PILE_KNOWLEDGE.items():
        item = {
            "code": name,
            "label": k.get("label", name),
            "category": k.get("category", ""),
            "applicability": k.get("applicability", ""),
            "not_considered": name in R.SELECTION_NOT_CONSIDERED,
            "preferred": name in R.PREFERRED_PILES,
        }
        if with_combos:
            item["combos"] = R.PILE_COMBOS.get(name, {})
        out.append(item)
    return out
