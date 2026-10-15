"""全平台统一枚举。

**这是三方共用的词汇表，任何一方都不得自行扩展。**
新增枚举值必须提 PR 改动本文件，并同步前端 frontend/src/constants/enums.ts。
"""
from __future__ import annotations

from enum import StrEnum


class StageCode(StrEnum):
    """7 个阶段。跨阶段数据互通的根本：同一实体在各阶段使用同一个 code。"""

    PRE_SURVEY = "PRE_SURVEY"        # 01 前期调研
    INVESTIGATION = "INVESTIGATION"  # 02 勘察
    DESIGN_TEST_PILE = "DESIGN_TEST_PILE"  # 03 设计试桩
    DESIGN = "DESIGN"                # 04 设计
    CONSTRUCTION = "CONSTRUCTION"    # 05 施工
    ACCEPT_TEST_PILE = "ACCEPT_TEST_PILE"  # 06 验收试桩
    MONITORING = "MONITORING"        # 07 运维监测


STAGE_ORDER: list[StageCode] = [
    StageCode.PRE_SURVEY,
    StageCode.INVESTIGATION,
    StageCode.DESIGN_TEST_PILE,
    StageCode.DESIGN,
    StageCode.CONSTRUCTION,
    StageCode.ACCEPT_TEST_PILE,
    StageCode.MONITORING,
]

STAGE_LABELS: dict[StageCode, str] = {
    StageCode.PRE_SURVEY: "前期调研",
    StageCode.INVESTIGATION: "勘察",
    StageCode.DESIGN_TEST_PILE: "设计试桩",
    StageCode.DESIGN: "设计",
    StageCode.CONSTRUCTION: "施工",
    StageCode.ACCEPT_TEST_PILE: "验收试桩",
    StageCode.MONITORING: "运维监测",
}


class StageStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SUSPENDED = "SUSPENDED"


class ProjectStatus(StrEnum):
    PREPARING = "PREPARING"      # 筹备
    IN_PROGRESS = "IN_PROGRESS"  # 进行中
    SUSPENDED = "SUSPENDED"      # 暂停
    COMPLETED = "COMPLETED"      # 已完成
    ARCHIVED = "ARCHIVED"        # 已归档


class OrgType(StrEnum):
    """参与单位类型 —— 描述"这是个什么单位"。"""

    OWNER = "OWNER"                      # 建设单位（业主）
    SURVEY = "SURVEY"                    # 勘察单位
    DESIGN_TEST_PILE = "DESIGN_TEST_PILE"  # 设计试桩单位
    DESIGN = "DESIGN"                    # 设计单位
    GENERAL_CONTRACTOR = "GENERAL_CONTRACTOR"  # 总包单位
    SUBCONTRACTOR = "SUBCONTRACTOR"      # 分包单位
    SUPERVISION = "SUPERVISION"          # 监理单位
    ACCEPT_TEST_PILE = "ACCEPT_TEST_PILE"  # 验收试桩单位
    INSPECTION_MONITORING = "INSPECTION_MONITORING"  # 检测监测单位
    GOVERNMENT = "GOVERNMENT"            # 政府审查单位（外部）
    PLATFORM = "PLATFORM"                # 平台方


class UnitCode(StrEnum):
    """全平台统一**参与单位**码。

    —— 主体是「单位 × 阶段 × 责任等级」，不是个人岗位。 ——

    为什么不用"设计人 / 校核人 / 审核人"这类岗位：
      1. 岗位是设计院内部的分工，平台管不到那一层；
      2. 同一个单位在不同阶段的责任不同，岗位说不清这件事；
      3. 责任要落到**单位**上 —— 文件丢了，找的是单位，不是某个人。

    单位内部的经办人由各单位自行指定，系统只保证
    **每一次操作都留下操作人与编号**，所以谁做的都查得到。
    """

    OWNER = "OWNER"                                  # 建设单位
    SURVEYOR = "SURVEYOR"                            # 勘察单位
    DESIGN_TEST_PILE = "DESIGN_TEST_PILE"            # 设计试桩单位
    DESIGNER = "DESIGNER"                            # 设计单位
    GENERAL_CONTRACTOR = "GENERAL_CONTRACTOR"        # 总包单位
    SUBCONTRACTOR = "SUBCONTRACTOR"                  # 分包单位
    SUPERVISOR = "SUPERVISOR"                        # 监理单位
    ACCEPT_TEST_PILE = "ACCEPT_TEST_PILE"            # 验收试桩单位
    INSPECTOR = "INSPECTOR"                          # 检测监测单位
    GOVERNMENT = "GOVERNMENT"                        # 政府审查单位
    ADMIN = "ADMIN"                                  # 系统管理员（平台角色）


UNIT_LABELS: dict[UnitCode, str] = {
    UnitCode.OWNER: "建设单位",
    UnitCode.SURVEYOR: "勘察单位",
    UnitCode.DESIGN_TEST_PILE: "设计试桩单位",
    UnitCode.DESIGNER: "设计单位",
    UnitCode.GENERAL_CONTRACTOR: "总包单位",
    UnitCode.SUBCONTRACTOR: "分包单位",
    UnitCode.SUPERVISOR: "监理单位",
    UnitCode.ACCEPT_TEST_PILE: "验收试桩单位",
    UnitCode.INSPECTOR: "检测监测单位",
    UnitCode.GOVERNMENT: "政府审查单位",
    UnitCode.ADMIN: "系统管理员",
}

# 参建单位（不含平台管理员），用于"选择参与单位"之类的界面
CONSTRUCTION_UNITS: list[UnitCode] = [u for u in UnitCode if u is not UnitCode.ADMIN]


class Responsibility(StrEnum):
    """责任等级 —— 由《管理流程》矩阵定义，不是我们发明的。

    矩阵里：√ = 参与，√* = 次要责任，√** = 主要责任。
    责任等级直接决定权限，所以不需要另外给每个角色配权限。
    """

    PRIMARY = "PRIMARY"          # ✓** 主要责任（主办）
    RELATED = "RELATED"          # ✓*  次要责任（相关）
    PARTICIPANT = "PARTICIPANT"  # ✓   参与
    VERIFIER = "VERIFIER"        # 政府审查单位：只读 + 写审查意见


RESPONSIBILITY_LABELS: dict[Responsibility, str] = {
    Responsibility.PRIMARY: "主要责任",
    Responsibility.RELATED: "次要责任",
    Responsibility.PARTICIPANT: "参与",
    Responsibility.VERIFIER: "审查",
}

# 责任等级强弱排序（数值越大责任越重），用于取"最高责任"
RESPONSIBILITY_ORDER: dict[Responsibility, int] = {
    Responsibility.VERIFIER: 0,
    Responsibility.PARTICIPANT: 1,
    Responsibility.RELATED: 2,
    Responsibility.PRIMARY: 3,
}


# ============================================================
# 《管理流程》权责矩阵 —— 全平台权限的唯一来源
# ============================================================
#
# 数据来源：项目《管理流程》表格（建设单位提供的参与方 × 阶段 职责矩阵）。
#
# **这张矩阵是数据，不是代码。** 之所以写在这里而不是散落到各处 if 判断里：
#   1. 责任划分要调整时，改这一处即可，不会漏改；
#   2. 权限从矩阵**推导**出来，不会出现"矩阵说监理负责、代码却拦住监理"的矛盾；
#   3. 汇报时可以直接把这张表打出来对。
#
# 读法：RESPONSIBILITY_MATRIX[阶段][单位] = 责任等级
#       某一阶段里没有列出的单位 = 该阶段无权限
#
RESPONSIBILITY_MATRIX: dict[str, dict[str, Responsibility]] = {
    StageCode.PRE_SURVEY.value: {
        UnitCode.OWNER.value: Responsibility.PRIMARY,
        UnitCode.SURVEYOR.value: Responsibility.PARTICIPANT,
        UnitCode.GOVERNMENT.value: Responsibility.RELATED,
    },
    StageCode.INVESTIGATION.value: {
        UnitCode.SURVEYOR.value: Responsibility.PRIMARY,
        UnitCode.OWNER.value: Responsibility.PARTICIPANT,
        UnitCode.SUPERVISOR.value: Responsibility.PARTICIPANT,
        UnitCode.GOVERNMENT.value: Responsibility.PARTICIPANT,
        # 设计单位：矩阵原表在此列未打 √，**经确认后补入**（2026-10-13）。
        # 理由：设计必须参照勘察资料。若不补，设计人员在系统里看不到勘察报告，
        # 设计输入文件库就是空的 —— 这是实际的业务缺口，不是权限设计问题。
        #
        # 定为 PARTICIPANT（只读），**不承担勘察阶段责任**。
        # 这也正对应"√"与"√*"的区别：参与 ≠ 责任 ——
        # 设计单位能查阅勘察成果，但勘察阶段的责任仍在勘察单位。
        #
        # ⚠️ 改这一行前先想清楚：删掉它，设计人员就查不到勘察报告了。
        #    scripts/test_ledger.py 第 10 组与 scripts/verify_objective.py
        #    都有断言守着这条，删掉会立刻失败。
        UnitCode.DESIGNER.value: Responsibility.PARTICIPANT,
    },
    StageCode.DESIGN_TEST_PILE.value: {
        UnitCode.DESIGN_TEST_PILE.value: Responsibility.PRIMARY,
        UnitCode.OWNER.value: Responsibility.PARTICIPANT,
        UnitCode.SURVEYOR.value: Responsibility.PARTICIPANT,
        UnitCode.DESIGNER.value: Responsibility.RELATED,
        UnitCode.GENERAL_CONTRACTOR.value: Responsibility.PARTICIPANT,
        UnitCode.SUPERVISOR.value: Responsibility.PARTICIPANT,
        UnitCode.INSPECTOR.value: Responsibility.PARTICIPANT,
        UnitCode.GOVERNMENT.value: Responsibility.RELATED,
    },
    StageCode.DESIGN.value: {
        UnitCode.DESIGNER.value: Responsibility.PRIMARY,
        UnitCode.OWNER.value: Responsibility.PARTICIPANT,
        UnitCode.SURVEYOR.value: Responsibility.PARTICIPANT,
        UnitCode.DESIGN_TEST_PILE.value: Responsibility.PARTICIPANT,
        UnitCode.GENERAL_CONTRACTOR.value: Responsibility.PARTICIPANT,
        UnitCode.SUBCONTRACTOR.value: Responsibility.PARTICIPANT,
        UnitCode.SUPERVISOR.value: Responsibility.RELATED,
        UnitCode.INSPECTOR.value: Responsibility.PARTICIPANT,
        UnitCode.GOVERNMENT.value: Responsibility.RELATED,
    },
    StageCode.CONSTRUCTION.value: {
        UnitCode.GENERAL_CONTRACTOR.value: Responsibility.PRIMARY,
        UnitCode.OWNER.value: Responsibility.PARTICIPANT,
        UnitCode.SURVEYOR.value: Responsibility.PARTICIPANT,
        UnitCode.DESIGNER.value: Responsibility.PARTICIPANT,
        UnitCode.SUBCONTRACTOR.value: Responsibility.RELATED,
        UnitCode.SUPERVISOR.value: Responsibility.RELATED,
        UnitCode.INSPECTOR.value: Responsibility.PARTICIPANT,
        UnitCode.GOVERNMENT.value: Responsibility.RELATED,
    },
    StageCode.ACCEPT_TEST_PILE.value: {
        UnitCode.ACCEPT_TEST_PILE.value: Responsibility.PRIMARY,
        UnitCode.OWNER.value: Responsibility.PARTICIPANT,
        UnitCode.SURVEYOR.value: Responsibility.PARTICIPANT,
        UnitCode.DESIGNER.value: Responsibility.RELATED,
        UnitCode.GENERAL_CONTRACTOR.value: Responsibility.PARTICIPANT,
        UnitCode.SUBCONTRACTOR.value: Responsibility.RELATED,
        UnitCode.SUPERVISOR.value: Responsibility.PARTICIPANT,
        UnitCode.INSPECTOR.value: Responsibility.PARTICIPANT,
    },
    StageCode.MONITORING.value: {
        UnitCode.INSPECTOR.value: Responsibility.PRIMARY,
        UnitCode.OWNER.value: Responsibility.RELATED,
        UnitCode.DESIGNER.value: Responsibility.PARTICIPANT,
    },
}


def responsibility_of(stage_code: str | None, unit_code: str | None) -> Responsibility | None:
    """查某单位在某阶段的责任等级。返回 None 表示该阶段无权限。

    这是权限判断的唯一入口 —— 别在别处再写一遍阶段×单位的对应关系。
    """
    if not stage_code or not unit_code:
        return None
    return RESPONSIBILITY_MATRIX.get(stage_code, {}).get(unit_code)


def units_of_stage(stage_code: str) -> dict[str, Responsibility]:
    """某阶段的全部参与单位及责任等级。"""
    return dict(RESPONSIBILITY_MATRIX.get(stage_code, {}))


def primary_unit_of_stage(stage_code: str) -> str | None:
    """某阶段的主办单位（主要责任）。每阶段有且只有一个。

    文件丢了找谁 —— 答案就是这个单位。
    """
    for unit, resp in RESPONSIBILITY_MATRIX.get(stage_code, {}).items():
        if resp is Responsibility.PRIMARY:
            return unit
    return None


def stages_of_unit(unit_code: str) -> dict[str, Responsibility]:
    """某单位参与的全部阶段及责任等级。"""
    out: dict[str, Responsibility] = {}
    for stage, units in RESPONSIBILITY_MATRIX.items():
        if unit_code in units:
            out[stage] = units[unit_code]
    return out


class DataScope(StrEnum):
    """数据范围。权限模型第 2 层。"""

    ALL = "ALL"              # 全部项目
    ORG = "ORG"              # 本组织及下级组织参与的项目
    ORG_ONLY = "ORG_ONLY"    # 仅本组织
    PROJECT = "PROJECT"      # 指定的若干项目
    STAGE = "STAGE"          # 指定项目 + 指定阶段
    SELF = "SELF"            # 仅本人创建/负责的数据


class SecretLevel(StrEnum):
    """敏感等级。定义在字典表里可调，代码中只引用不硬编码判断。"""

    PUBLIC = "PUBLIC"          # 公开
    INTERNAL = "INTERNAL"      # 内部
    RESTRICTED = "RESTRICTED"  # 受限（需 document_access 显式授权）
    SECRET = "SECRET"          # 保密（需授权 + 下载留痕 + 不可批量导出）


SECRET_ORDER: dict[SecretLevel, int] = {
    SecretLevel.PUBLIC: 0,
    SecretLevel.INTERNAL: 1,
    SecretLevel.RESTRICTED: 2,
    SecretLevel.SECRET: 3,
}


class VerifyStatus(StrEnum):
    """设计输入参数的核验状态。

    STALE 是**自动推导**出来的：当参数的来源文件发布了新版本，
    原核验结论就不再成立，必须重新核验 —— 这正是"勘察报告更新了，
    设计根本不知道"这个工程风险的机制化防线。
    """

    PENDING = "PENDING"      # 待核验
    VERIFIED = "VERIFIED"    # 已核验
    MODIFIED = "MODIFIED"    # 已修改（人工调整过取值）
    DOUBTFUL = "DOUBTFUL"    # 存疑（需资料提供方澄清）
    STALE = "STALE"          # 来源已失效（源文件发布了新版本，需重新核验）


VERIFY_STATUS_LABELS: dict[VerifyStatus, str] = {
    VerifyStatus.PENDING: "待核验",
    VerifyStatus.VERIFIED: "已核验",
    VerifyStatus.MODIFIED: "已修改",
    VerifyStatus.DOUBTFUL: "存疑",
    VerifyStatus.STALE: "来源已失效",
}


class DocumentState(StrEnum):
    """文件版本状态机。

    草稿 → 校核中 → 审核中 → 已批准 → 已发布 → 已作废
    修订循环：已发布 --发起修订--> 修订中 --> 校核中 ...
    """

    DRAFT = "DRAFT"              # 草稿
    CHECKING = "CHECKING"        # 校核中
    REVIEWING = "REVIEWING"      # 审核中
    APPROVED = "APPROVED"        # 已批准
    REVISING = "REVISING"        # 修订中
    PUBLISHED = "PUBLISHED"      # 已发布 —— 唯一可被下游引用的状态
    VOID = "VOID"                # 已作废/归档


DOCUMENT_STATE_LABELS: dict[DocumentState, str] = {
    DocumentState.DRAFT: "草稿",
    DocumentState.CHECKING: "校核中",
    DocumentState.REVIEWING: "审核中",
    DocumentState.APPROVED: "已批准",
    DocumentState.REVISING: "修订中",
    DocumentState.PUBLISHED: "已发布",
    DocumentState.VOID: "已作废",
}

# 处于审批流程中、不可被引用的状态
NON_PUBLISHABLE_STATES = {
    DocumentState.DRAFT,
    DocumentState.CHECKING,
    DocumentState.REVIEWING,
    DocumentState.REVISING,
    DocumentState.APPROVED,
}


class ChangeState(StrEnum):
    """设计变更状态机。

    待提交 → 影响分析中 → 待审批 → 审批中 → 已批准 → 执行中 → 已关闭
                                        └→ 已驳回
    """

    DRAFT = "DRAFT"                    # 待提交
    IMPACT_ANALYZING = "IMPACT_ANALYZING"  # 影响分析中
    PENDING_APPROVAL = "PENDING_APPROVAL"  # 待审批
    APPROVING = "APPROVING"            # 审批中
    APPROVED = "APPROVED"              # 已批准
    REJECTED = "REJECTED"              # 已驳回
    EXECUTING = "EXECUTING"            # 执行中
    CLOSED = "CLOSED"                  # 已关闭


CHANGE_STATE_LABELS: dict[ChangeState, str] = {
    ChangeState.DRAFT: "待提交",
    ChangeState.IMPACT_ANALYZING: "影响分析中",
    ChangeState.PENDING_APPROVAL: "待审批",
    ChangeState.APPROVING: "审批中",
    ChangeState.APPROVED: "已批准",
    ChangeState.REJECTED: "已驳回",
    ChangeState.EXECUTING: "执行中",
    ChangeState.CLOSED: "已关闭",
}


class ChangeCategory(StrEnum):
    """变更原因分类。必须做成字典项，用于后期统计变更来源。"""

    SURVEY_DATA = "SURVEY_DATA"      # 勘察资料变化
    OWNER_REQUEST = "OWNER_REQUEST"  # 业主要求
    CODE_UPDATE = "CODE_UPDATE"      # 规范更新
    SITE_CONDITION = "SITE_CONDITION"  # 施工条件
    DESIGN_OPTIMIZE = "DESIGN_OPTIMIZE"  # 设计优化


CHANGE_CATEGORY_LABELS: dict[ChangeCategory, str] = {
    ChangeCategory.SURVEY_DATA: "勘察资料变化",
    ChangeCategory.OWNER_REQUEST: "业主要求",
    ChangeCategory.CODE_UPDATE: "规范更新",
    ChangeCategory.SITE_CONDITION: "施工条件",
    ChangeCategory.DESIGN_OPTIMIZE: "设计优化",
}


class ImpactTargetType(StrEnum):
    """变更影响对象类型。"""

    PILE = "PILE"                    # 桩位
    CALCULATION = "CALCULATION"      # 计算书
    DRAWING = "DRAWING"              # 图纸
    CONSTRUCTED_PART = "CONSTRUCTED_PART"  # 已施工部位 —— 高风险，需立即通知
    COST = "COST"                    # 成本
    SCHEDULE = "SCHEDULE"            # 进度


IMPACT_TARGET_LABELS: dict[ImpactTargetType, str] = {
    ImpactTargetType.PILE: "受影响桩位",
    ImpactTargetType.CALCULATION: "计算书",
    ImpactTargetType.DRAWING: "图纸",
    ImpactTargetType.CONSTRUCTED_PART: "已施工部位",
    ImpactTargetType.COST: "成本",
    ImpactTargetType.SCHEDULE: "进度",
}


class IssueStatus(StrEnum):
    OPEN = "OPEN"              # 待处理
    IN_PROGRESS = "IN_PROGRESS"  # 处理中
    PENDING_VERIFY = "PENDING_VERIFY"  # 待验证
    CLOSED = "CLOSED"          # 已闭环
    ESCALATED = "ESCALATED"    # 已升级


ISSUE_STATUS_LABELS: dict[IssueStatus, str] = {
    IssueStatus.OPEN: "待处理",
    IssueStatus.IN_PROGRESS: "处理中",
    IssueStatus.PENDING_VERIFY: "待验证",
    IssueStatus.CLOSED: "已闭环",
    IssueStatus.ESCALATED: "已升级",
}


class IssueActionType(StrEnum):
    """问题处理链路 —— 对应设计 PPT 第 8 页那条链路。

    问题描述 → 查询 → 分析识别 → 建议 → 执行 → 验证 → 闭环 → 知识沉淀

    **这条链要有表承载，不能只做在聊天窗口里。**
    最后一步"知识沉淀"是产品越用越有价值的关键。
    """

    DESCRIBE = "DESCRIBE"      # 问题描述
    QUERY = "QUERY"            # 查询（规范/历史案例/AI 检索）
    ANALYZE = "ANALYZE"        # 分析识别（原因分类）
    SUGGEST = "SUGGEST"        # 建议（AI 生成候选方案 + 依据）
    EXECUTE = "EXECUTE"        # 执行（责任人 + 期限）
    VERIFY = "VERIFY"          # 验证（谁验证、依据什么、结论）
    CLOSE = "CLOSE"            # 闭环
    KNOWLEDGE = "KNOWLEDGE"    # 知识沉淀


ISSUE_ACTION_LABELS: dict[IssueActionType, str] = {
    IssueActionType.DESCRIBE: "问题描述",
    IssueActionType.QUERY: "查询",
    IssueActionType.ANALYZE: "分析识别",
    IssueActionType.SUGGEST: "建议",
    IssueActionType.EXECUTE: "执行",
    IssueActionType.VERIFY: "验证",
    IssueActionType.CLOSE: "闭环",
    IssueActionType.KNOWLEDGE: "知识沉淀",
}

# 处理链路的推进顺序。用于校验"不能跳步"。
ISSUE_ACTION_ORDER: list[IssueActionType] = [
    IssueActionType.DESCRIBE,
    IssueActionType.QUERY,
    IssueActionType.ANALYZE,
    IssueActionType.SUGGEST,
    IssueActionType.EXECUTE,
    IssueActionType.VERIFY,
    IssueActionType.CLOSE,
    IssueActionType.KNOWLEDGE,
]


class IssueSource(StrEnum):
    """问题来源。"""

    REVIEW = "REVIEW"          # 校审
    SITE = "SITE"              # 现场
    INSPECTION = "INSPECTION"  # 检测
    SELF = "SELF"              # 自检
    MONITOR = "MONITOR"        # 监测
    AI = "AI"                  # AI 提示


ISSUE_SOURCE_LABELS: dict[IssueSource, str] = {
    IssueSource.REVIEW: "校审",
    IssueSource.SITE: "现场",
    IssueSource.INSPECTION: "检测",
    IssueSource.SELF: "自检",
    IssueSource.MONITOR: "监测",
    IssueSource.AI: "AI 提示",
}


class Severity(StrEnum):
    """风险/严重程度。问题、变更影响、监测告警共用。"""

    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


SEVERITY_LABELS: dict[Severity, str] = {
    Severity.HIGH: "高",
    Severity.NORMAL: "中",
    Severity.LOW: "低",
}


class WorkflowBizType(StrEnum):
    REVIEW = "REVIEW"     # 校审
    CHANGE = "CHANGE"     # 变更
    PUBLISH = "PUBLISH"   # 发布


class WorkflowStatus(StrEnum):
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    CANCELED = "CANCELED"


class TaskAction(StrEnum):
    APPROVE = "APPROVE"  # 通过
    RETURN = "RETURN"    # 退回修改
    REJECT = "REJECT"    # 驳回


class WorkflowNodeCode(StrEnum):
    """流程节点。

    新方向是**两级签认**（不是原设计院的三级校审）：

        CONFIRM  主办单位确认 —— 提交人对本单位文件负责
        REVIEW   相关单位复核 —— 次要责任单位必须过一遍
        VERIFY   审查单位意见 —— 政府审查单位，只提意见不签认

    为什么从三级（校核/审核/批准）降为两级：
      主体改为「单位」之后，校核人与审核人往往同属设计院，
      平台无法也不该管到单位内部分工。两级 = 主办单位 + 相关单位，
      正好对应《管理流程》矩阵里每列的 ** 与 *。
      责任落点反而更清楚：文件丢了，找主办单位。
    """

    CONFIRM = "CONFIRM"    # 主办单位确认
    REVIEW = "REVIEW"      # 相关单位复核
    VERIFY = "VERIFY"      # 审查单位提意见（政府审查）
    PUBLISH = "PUBLISH"    # 发布（由主办单位执行，不是审批节点）
    SELF_CHECK = "SELF_CHECK"  # 兼容保留：单位内自行确认，必须留痕


WORKFLOW_NODE_LABELS: dict[WorkflowNodeCode, str] = {
    WorkflowNodeCode.CONFIRM: "主办单位确认",
    WorkflowNodeCode.REVIEW: "相关单位复核",
    WorkflowNodeCode.VERIFY: "审查意见",
    WorkflowNodeCode.PUBLISH: "发布",
    WorkflowNodeCode.SELF_CHECK: "单位内自校",
}


class PermissionAction(StrEnum):
    """权限动作。

    动作**不是单独配给角色的，而是从责任等级推导**（见 core/permissions.py）：

        主办（**）→ 查看 下载 编辑 提交 发布 签认
        相关（*） → 查看 下载 签认 提意见
        参与（√） → 查看 下载
        审查      → 查看 下载 提意见

    这样责任划分一改，权限自动跟着变，不会出现两处不一致。
    注意 EXPORT 已按讨论去掉 —— 导出与下载的区分在"以单位为主体"下
    意义不大，且清单不是真正的交付物。值保留仅为兼容旧数据。
    """

    VIEW = "VIEW"            # 查看（列表、详情、元数据）
    DOWNLOAD = "DOWNLOAD"    # 下载文件内容
    EDIT = "EDIT"            # 新建 / 修改 / 上传新版本
    SUBMIT = "SUBMIT"        # 提交签认（把文件推给相关单位复核）
    PUBLISH = "PUBLISH"      # 发布（发布后不可回退，只能发新版本）
    CONFIRM = "CONFIRM"      # 签认（确认本单位对这份文件负责 / 复核通过）
    COMMENT = "COMMENT"      # 提意见（不签认）
    EXPORT = "EXPORT"        # 【已停用】保留值以便兼容历史数据


PERMISSION_ACTION_LABELS: dict[PermissionAction, str] = {
    PermissionAction.VIEW: "查看",
    PermissionAction.DOWNLOAD: "下载",
    PermissionAction.EDIT: "编辑",
    PermissionAction.SUBMIT: "提交",
    PermissionAction.PUBLISH: "发布",
    PermissionAction.CONFIRM: "签认",
    PermissionAction.COMMENT: "提意见",
    PermissionAction.EXPORT: "导出",
}


# ============================================================
# 兼容别名（过渡期用）
# ============================================================
# 旧代码里的"岗位角色"概念已被"参与单位"取代。
# 保留这两个别名，让尚未改造的模块仍能 import，不至于整片报错。
# **新代码请直接用 UnitCode / UNIT_LABELS，不要用这两个别名。**
RoleCode = UnitCode
ROLE_LABELS = UNIT_LABELS
