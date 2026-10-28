"""桩基选型知识库与规则常量。

来源：桌面「选型」软件（`选型/platform/config.py`）中与**选型**相关的那部分，
只搬运决策所需的知识库与规则，不含报告生成/LLM 解析/CAD 提取等外围能力。

**修改这里的数值即可全局生效。** 所有取值均为方案阶段假定，
最终以正式勘察报告及桩基规范计算结果为准。

约定（与原软件保持一致，勿随意改动，否则历史结论会对不上）：
- 评分 1~5，越大越好；
- 区间桩径（如 500/600）一律**取小值**；
- `metros` 是选型图内「保护区/地铁保护区」的直标值，不按区间取小。
"""
from __future__ import annotations

# ============================================================
# 一、桩型知识库（七维评分，1~5）
# ============================================================

SCORE_DIMENSIONS: list[str] = [
    "工程成本",
    "施工工期",
    "挤土效应",
    "施工噪声",
    "承载力",
    "技术成熟度",
    "适用性匹配",
]

#: 桩型 → 基本信息与评分。key 同时是选型接口里使用的桩型编码。
PILE_KNOWLEDGE: dict[str, dict] = {
    "钻孔灌注桩": {
        "name": "钻孔灌注桩",
        "category": "非挤土桩",
        "label": "钻孔灌注桩",
        "scores": {"工程成本": 1, "施工工期": 2, "挤土效应": 5, "施工噪声": 5,
                   "承载力": 5, "技术成熟度": 5, "适用性匹配": 5},
        "applicability": "上海地区基本均可采用",
    },
    "钻孔灌注桩(端注浆)": {
        "name": "钻孔灌注桩(端注浆)",
        "category": "非挤土桩",
        "label": "钻孔灌注桩（桩端后注浆）",
        "scores": {"工程成本": 1, "施工工期": 2, "挤土效应": 5, "施工噪声": 5,
                   "承载力": 5, "技术成熟度": 5, "适用性匹配": 4},
        "applicability": "塔楼等承压工况控制的单体（注浆量一般3~5倍桩径）",
    },
    "根植桩": {
        "name": "根植桩",
        "category": "非挤土桩",
        "label": "根植桩",
        "scores": {"工程成本": 2, "施工工期": 2, "挤土效应": 4, "施工噪声": 5,
                   "承载力": 4, "技术成熟度": 2, "适用性匹配": 2},
        "applicability": "对挤土效应要求高的承压控制区域（非塔楼不推荐）",
    },
    "PHC预应力混凝土管桩": {
        "name": "PHC预应力混凝土管桩",
        "category": "挤土桩",
        "label": "PHC预应力管桩",
        "scores": {"工程成本": 5, "施工工期": 5, "挤土效应": 1, "施工噪声": 1,
                   "承载力": 2, "技术成熟度": 5, "适用性匹配": 3},
        "applicability": "对挤土效应要求低的区域",
    },
    "UHC高性能管桩": {
        "name": "UHC高性能管桩",
        "category": "挤土桩",
        "label": "UHC高性能管桩",
        "scores": {"工程成本": 4, "施工工期": 5, "挤土效应": 1, "施工噪声": 1,
                   "承载力": 4, "技术成熟度": 4, "适用性匹配": 2},
        "applicability": "对挤土效应要求低的50m以上塔楼",
    },
    "PHS预应力混凝土空心方桩": {
        "name": "PHS预应力混凝土空心方桩",
        "category": "挤土桩",
        "label": "预应力空心方桩",
        "scores": {"工程成本": 3, "施工工期": 5, "挤土效应": 1, "施工噪声": 1,
                   "承载力": 2, "技术成熟度": 4, "适用性匹配": 2},
        "applicability": "对挤土效应要求低的抗拔控制区域",
    },
    "预制实心方桩": {
        "name": "预制实心方桩",
        "category": "挤土桩",
        "label": "预应力实心方桩",
        "scores": {"工程成本": 3, "施工工期": 5, "挤土效应": 1, "施工噪声": 1,
                   "承载力": 2, "技术成熟度": 4, "适用性匹配": 2},
        "applicability": "对挤土效应要求低的抗拔控制区域",
    },
}

#: 挤土桩：受限场景（地铁保护区等）必须排除
DISPLACEMENT_PILES: list[str] = [
    "PHC预应力混凝土管桩",
    "UHC高性能管桩",
    "PHS预应力混凝土空心方桩",
    "预制实心方桩",
]

#: 选型阶段暂不考虑的桩型：不参与评分推荐，但保留在校对表下拉里供人工选择
SELECTION_NOT_CONSIDERED: tuple[str, ...] = ("UHC高性能管桩",)

#: 优选桩型：排序时排在其他桩型之前（同层内仍按评分排）
PREFERRED_PILES: tuple[str, ...] = ("PHC预应力混凝土管桩", "钻孔灌注桩(端注浆)")

#: 项目条件字段 → 中文标签（前端表单与后端校验共用）
CONDITION_LABELS: dict[str, str] = {
    "metro_protection_zone": "地铁 50m 安全保护区",
    "inner_ring": "内环以内",
    "near_viaduct_bridge": "临近高架/桥梁",
    "dense_buildings_nearby": "周边建筑密集",
    "noise_sensitive": "噪声敏感",
    "tight_schedule": "工期紧张",
    "tight_budget": "成本敏感",
    "env_protection_strict": "环保要求严格",
    "has_sand_layer": "存在砂层",
    "need_permanent_temp_combo": "永久+临时立柱桩结合",
    "has_inner_support": "设内支撑",
}

#: 布尔型项目条件（其余为数值型：basement_floors / tower_max_floors / tower_max_height_m）
CONDITION_FLAGS: tuple[str, ...] = tuple(CONDITION_LABELS.keys())

# ============================================================
# 二、选型权重（两个场景）
# ============================================================

WEIGHTS_RESTRICTED: dict[str, float] = {
    "工程成本": 1.0, "施工工期": 0.8, "挤土效应": 1.2, "施工噪声": 0.6,
    "承载力": 1.0, "技术成熟度": 0.8, "适用性匹配": 1.0,
}
WEIGHTS_ECONOMY: dict[str, float] = {
    "工程成本": 2.5, "施工工期": 2.0, "挤土效应": 0.4, "施工噪声": 0.4,
    "承载力": 0.8, "技术成熟度": 0.6, "适用性匹配": 1.0,
}

# ============================================================
# 三、典型桩参数组合（历史项目方案值，作为勘察数据缺失时的兜底）
#     main=主楼承压桩，base_B1/B2=地下一层/两层范围承压兼抗拔桩
# ============================================================

PILE_COMBOS: dict[str, dict[str, dict]] = {
    "钻孔灌注桩(端注浆)": {
        "main": {"desc": "灌注桩，桩端后注浆", "short": "Φ800钻孔灌注桩",
                 "d_mm": 800, "lengths": "45m", "capacity_t": 390,
                 "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
        "base_B1": {"desc": "直径600mm，灌注桩", "short": "Φ600钻孔灌注桩",
                    "d_mm": 600, "lengths": "35m", "uplift_t": 100,
                    "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
        "base_B2": {"desc": "直径600mm，灌注桩", "short": "Φ600钻孔灌注桩",
                    "d_mm": 600, "lengths": "35m", "uplift_t": 100,
                    "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
    },
    "钻孔灌注桩": {
        "main": {"desc": "灌注桩", "short": "Φ800钻孔灌注桩",
                 "d_mm": 800, "lengths": "45m", "capacity_t": 230,
                 "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
        "base_B1": {"desc": "直径600mm，灌注桩", "short": "Φ600钻孔灌注桩",
                    "d_mm": 600, "lengths": "35m", "uplift_t": 100,
                    "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
        "base_B2": {"desc": "直径600mm，灌注桩", "short": "Φ600钻孔灌注桩",
                    "d_mm": 600, "lengths": "35m", "uplift_t": 100,
                    "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
    },
    "PHC预应力混凝土管桩": {
        "main": {"desc": "PHC 500（125）AB 管桩", "short": "PHC 500（125）AB",
                 "d_mm": 500, "lengths": "46m/42m", "capacity_t": 190,
                 "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
        "base_B1": {"desc": "PHC 400（95）AB 管桩", "short": "PHC 400（95）AB",
                    "d_mm": 400, "lengths": "26m", "uplift_t": 50,
                    "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
        "base_B2": {"desc": "PHC 500（125）AB 管桩", "short": "PHC 500（125）AB",
                    "d_mm": 500, "lengths": "30m", "uplift_t": 80,
                    "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
    },
    "UHC高性能管桩": {
        "main": {"desc": "UHC-500（125）AB 管桩", "short": "UHC-500（125）AB",
                 "d_mm": 500, "lengths": "46m", "capacity_t": 230,
                 "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
        "base_B1": {"desc": "UHC-400（95）AB 管桩", "short": "UHC-400（95）AB",
                    "d_mm": 400, "lengths": "26m", "uplift_t": 55,
                    "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
        "base_B2": {"desc": "UHC-500（125）AB 管桩", "short": "UHC-500（125）AB",
                    "d_mm": 500, "lengths": "30m", "uplift_t": 90,
                    "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
    },
    "PHS预应力混凝土空心方桩": {
        "main": {"desc": "PHS500AB预应力混凝土空心方桩", "short": "PHS500AB",
                 "d_mm": 500, "lengths": "40m", "capacity_t": 170,
                 "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
        "base_B1": {"desc": "PHS400AB预应力混凝土空心方桩", "short": "PHS400AB",
                    "d_mm": 400, "lengths": "24m", "uplift_t": 45,
                    "layer": "⑦₁₋₁", "layer_desc": "粉土夹粘性土"},
        "base_B2": {"desc": "PHS500AB预应力混凝土空心方桩", "short": "PHS500AB",
                    "d_mm": 500, "lengths": "30m", "uplift_t": 80,
                    "layer": "⑦₁₋₁", "layer_desc": "粉土夹粘性土"},
    },
    "预制实心方桩": {
        "main": {"desc": "YZH500A预应力混凝土实心方桩", "short": "YZH500A",
                 "d_mm": 500, "lengths": "36m", "capacity_t": 140,
                 "layer": "⑦₁₋₁", "layer_desc": "粉土夹粘性土"},
        "base_B1": {"desc": "YZH400B预应力混凝土实心方桩", "short": "YZH400B",
                    "d_mm": 400, "lengths": "24m", "uplift_t": 40,
                    "layer": "⑦₁₋₁", "layer_desc": "粉土夹粘性土"},
        "base_B2": {"desc": "YZH500A预应力混凝土实心方桩", "short": "YZH500A",
                    "d_mm": 500, "lengths": "30m/26m", "uplift_t": 80,
                    "layer": "⑦₁₋₁", "layer_desc": "粉土夹粘性土"},
    },
    "根植桩": {
        "main": {"desc": "根植桩", "short": "Φ600根植桩",
                 "d_mm": 600, "lengths": "48m", "capacity_t": 280,
                 "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
        "base_B1": {"desc": "根植桩", "short": "Φ500根植桩",
                    "d_mm": 500, "lengths": "28m", "uplift_t": 70,
                    "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
        "base_B2": {"desc": "根植桩", "short": "Φ500根植桩",
                    "d_mm": 500, "lengths": "30m", "uplift_t": 80,
                    "layer": "⑦₂", "layer_desc": "灰黄~灰色粉砂"},
    },
}

# ============================================================
# 四、桩径选择规则（院版《桩基方案》第五、六章选型图口径）
# ============================================================

#: 主楼高度带序号
BAND_LOWRISE = 0    # 低多层 1-6F
BAND_MIDRISE = 1    # 中高层 7-9F
BAND_HIGHRISE = 2   # 高层 10F~100m
BAND_SUPERHIGH = 3  # 超高层 >100m

BAND_LABELS: dict[int, str] = {
    BAND_LOWRISE: "低多层（1-6F）",
    BAND_MIDRISE: "中高层（7-9F）",
    BAND_HIGHRISE: "高层（10F~100m）",
    BAND_SUPERHIGH: "超高层（>100m）",
}

DIAMETER_RULES: dict[str, dict] = {
    "main": {
        # 图一（受限选型图）：低多层/中高层 600 直标；高层 600/700→600、
        # 超高层 700/800→700（区间取小）；metros = 图内"保护区/地铁保护区"直标值
        "restricted": {
            "钻孔灌注桩": {"base": [600, 600, 600, 700], "metros": [600, 700, 800, 850]},
            "钻孔灌注桩(端注浆)": {"base": [600, 600, 600, 700], "metros": [600, 700, 800, 850]},
            "根植桩": {"base": [600, 600, 600, 800], "metros": [600, 750, 800, 800]},
        },
        # 图二（非受限选型图）：区间桩径取小值
        "economy": {
            "PHC预应力混凝土管桩": [400, 500, 500, 500],
            "UHC高性能管桩": [400, 500, 600, 700],
            "PHS预应力混凝土空心方桩": [400, 500, 500, 500],
            "预制实心方桩": [400, 500, 500, 500],
            "钻孔灌注桩": [600, 600, 600, 700],
            "钻孔灌注桩(端注浆)": [600, 600, 700, 700],
            "根植桩": [600, 600, 600, 800],
        },
    },
    "base": {
        # 图三~图五（地下层数选型图）：B1/B2/B3 各桩型建议桩径
        "钻孔灌注桩": {"B1": 600, "B2": 600, "B3": 600},
        "钻孔灌注桩(端注浆)": {"B1": 600, "B2": 600, "B3": 600},
        "PHC预应力混凝土管桩": {"B1": 400, "B2": 500, "B3": 500},
        "UHC高性能管桩": {"B1": 400, "B2": 500, "B3": 500},
        "PHS预应力混凝土空心方桩": {"B1": 400, "B2": 400, "B3": 400},
        "预制实心方桩": {"B1": 400, "B2": 400, "B3": 400},
        "根植桩": {"B1": 600, "B2": 600, "B3": 600},
    },
}

#: 桩径与典型组合不一致时，按桩型重生成短名/描述
#: wall = 各直径对应壁厚（mm，PHC 按 GB/T 13476；UHC 按上海市标常用规格）
PILE_LABEL_BY_TYPE: dict[str, dict] = {
    "钻孔灌注桩": {"short": "Φ{d}钻孔灌注桩", "desc": "灌注桩",
                   "base_desc": "直径{d}mm，灌注桩"},
    "钻孔灌注桩(端注浆)": {"short": "Φ{d}钻孔灌注桩", "desc": "灌注桩，桩端后注浆",
                           "base_desc": "直径{d}mm，灌注桩"},
    "根植桩": {"short": "Φ{d}根植桩", "desc": "根植桩", "base_desc": "根植桩"},
    "PHC预应力混凝土管桩": {"short": "PHC {d}（{t}）AB", "desc": "PHC {d}（{t}）AB 管桩",
                            "base_desc": "PHC {d}（{t}）AB 管桩",
                            "wall": {400: 95, 500: 125, 600: 110}},
    "UHC高性能管桩": {"short": "UHC-{d}（{t}）AB", "desc": "UHC-{d}（{t}）AB 管桩",
                      "base_desc": "UHC-{d}（{t}）AB 管桩",
                      "wall": {400: 95, 500: 125, 600: 130, 700: 140, 800: 150}},
    "PHS预应力混凝土空心方桩": {"short": "PHS{d}AB", "desc": "PHS{d}AB预应力混凝土空心方桩",
                                "base_desc": "PHS{d}AB预应力混凝土空心方桩"},
    "预制实心方桩": {"short": "YZH{d}A", "desc": "YZH{d}A预应力混凝土实心方桩",
                     "base_desc": "YZH{d}B预应力混凝土实心方桩"},
}

#: 「勘察报告优先」口径下的可信桩径（非标值回落选型图规则，防 OCR 误读）
REPORT_D_CAST: tuple[int, ...] = (500, 600, 700, 750, 800, 850, 900, 1000)
REPORT_D_PREFAB: tuple[int, ...] = (400, 500, 600)
CAST_TYPES: tuple[str, ...] = ("钻孔灌注桩", "钻孔灌注桩(端注浆)", "根植桩")


# ============================================================
# 五、桩数估算假定（2024 院版口径，来源同原「选型」软件 config.py）
# ============================================================

LOAD_ABOVEGROUND_T_M2 = 1.7     # 地上重力荷载标准值（吨/平米，按地上建筑面积）
REDUND_PCT = 20                 # 重力/浮力荷载冗余度（%）

#: 地下室抗拔承载力需求公式常量
BASEMENT_H_SINGLE_M = 4.0       # 挖深缺省：地下室暂估层高（m）
BASEMENT_H_DOUBLE_M = 4.0       # 两层地下室每层挖深缺省（m）
SLAB_TOP_M = 0.4                # 顶板折算厚度（m）
SLAB_MID_M = 0.25               # 中板折算厚度（m）
SLAB_BOTTOM_SINGLE_M = 0.6      # 单层地下室底板折算厚度（m）
SLAB_BOTTOM_DOUBLE_M = 0.8      # 双层地下室底板折算厚度（m）
COVER_BUOY_M = 1.5              # 覆土厚度缺省（m）
COVER_WATER_BUOY_M = 0.1        # 覆土厚度内水头高（m）
BUOY_HEAD_M = 1.0               # 抗浮水头高（m）
COVER_REDUCE_BUOY = 0.9         # 覆土重折减系数
WATER_DENS_T_M3 = 1.0           # 水密度（吨/立方米）
CONC_DENS_T_M3 = 2.5            # 混凝土容重（吨/立方米）
COVER_DENS_T_M3 = 1.6           # 覆土密度（吨/立方米）
FOS_BUOYANCY = 1.1              # 抗浮稳定系数

#: 柱网与桩数取整方式（历史报告多向下取整；古美双层拆分处为四舍五入）
GRID_X_M = 6.0
GRID_Y_M = 6.0
PILE_COUNT_ROUND = "floor"      # 主楼桩数总数：floor / round / ceil
BASE_COUNT_ROUND = "ceil"       # 非主楼桩数向上取整（院版口径）
SPLIT_ROUND = "round"           # 主楼双层/单层拆分
DENSITY_ROUND = "round"         # 每千平米桩数

#: 报告措辞
CAP_TERM = "设计值"              # 承载力术语：设计值 / 特征值（院习惯）
CAP_UNIT_MAIN = "吨"
CAP_UNIT_BASE = "吨"

REMARK_ITEMS: list[str] = [
    "主楼范围承压桩估算考虑低水位水浮力与主楼地下室自重基本抵消，未考虑周边地下室抗浮对承压的有利贡献；",
    "地下室范围抗拔桩估算未考虑主楼范围内承压对抗浮的有利贡献；",
    "承压桩重力荷载和抗拔桩浮力荷载冗余度按照{red}%考虑。",
]

#: 勘察参数自洽性判定阈值（与缺省经验值 75/2300 比对）
FS_RANGE: tuple[float, float] = (60, 90)
FP_RANGE: tuple[float, float] = (1840, 2760)
