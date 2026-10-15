"""数据库结构快速检查。

**这个脚本对三个人协作特别有用**：它会比对「ORM 模型」与「数据库实际表」，
一眼看出"你加了模型但忘了建表/生成迁移"。

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/check_db.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402


def main() -> int:
    # 先加载全部模型，拿到 ORM 认为应该存在的表
    import app.models  # noqa: F401
    from app.models.base import Base

    orm_tables = set(Base.metadata.tables.keys())

    if not settings.DATABASE_URL.startswith("sqlite"):
        print("当前数据库不是 SQLite，跳过本地结构检查：", settings.DATABASE_URL)
        return 0

    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    if not Path(db_path).exists():
        print("数据库文件不存在，请先执行：")
        print("    .venv\\Scripts\\python.exe -m app.seed.seed_all --reset")
        print("或  alembic upgrade head")
        print("路径：", db_path)
        return 1

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
    business = set(t for t in tables if t != "alembic_version")

    print(f"数据库文件   : {db_path}")
    print(f"ORM 模型表数 : {len(orm_tables)}")
    print(f"数据库实际表 : {len(business)}")
    print(f"迁移版本     : ", end="")
    row = cur.execute("SELECT version_num FROM alembic_version").fetchone()
    print(row[0] if row else "(未应用迁移)")
    print()

    # ---------- 核心检查：ORM 与数据库是否一致 ----------
    # 只差 1~2 张表时给出明确指引，而不是一句"缺失"
    missing_in_db = sorted(orm_tables - business)
    extra_in_db = sorted(business - orm_tables)

    ok = True

    if missing_in_db:
        ok = False
        print("!! 以下表在 ORM 模型里有、数据库里没有：")
        for t in missing_in_db:
            print(f"     {t}   <== 需要建表")
        print()
        print("   原因通常是：加了模型但表结构没同步。")
        print()
        print("   【注意】seed_all --reset **只清数据、不重建表结构**。")
        print("           表不存在时必须先用迁移建表：")
        print("       .venv\\Scripts\\python.exe -m alembic upgrade head")
        print()
        print("   若迁移里还没有你的新表，说明迁移文件还没生成 ——")
        print("   见《协作入门.md》第 4 节「加数据模型的正确姿势」。")
        print()

    if extra_in_db:
        # 多余表不一定算错（可能是别人加的、你还没合并代码），但要提示
        print("·· 以下表在数据库里有、ORM 模型里没有：")
        for t in extra_in_db:
            print(f"     {t}")
        print("   通常是队友已合并的模型、但你本地代码还没更新。")
        print("   拉取最新代码后重新建库即可：")
        print("       .venv\\Scripts\\python.exe -m app.seed.seed_all --reset")
        print()

    # ---------- 按域分组展示，便于人工核对 ----------
    groups = {
        "字典（统一 ID）": ["dict_category", "dict_item"],
        "组织与用户": ["organization", "app_user", "user_org"],
        "项目与专业对象": [
            "project", "project_stage", "project_member",
            "soil_layer", "soil_property", "design_param", "pile",
        ],
        "文件与版本": [
            "file_object", "document", "document_version",
            "document_relation", "document_access",
        ],
        "流程与审批": ["workflow_template", "workflow_instance", "workflow_task"],
        "变更": ["change_request", "change_impact"],
        "问题": ["issue", "issue_action"],
        # 说明：原「成本与进度」4 张 + 「监测」4 张共 12 张表已移除。
        # 平台核心是文档管理（文件易丢、责任难追），不做成本与进度；
        # 监测结果以**文件**形式归档，不需要结构化点位表。
        # 详见 app/models/__init__.py 顶部说明。
        "AI 与审计": ["knowledge_chunk", "ai_conversation", "ai_message", "ai_citation", "audit_log"],
    }
    # 已分组的表从"其它"里排除
    grouped = {n for names in groups.values() for n in names}
    others = sorted(orm_tables - grouped)
    if others:
        groups["其它（各阶段新增）"] = others

    print("按域分组：")
    for group, names in groups.items():
        present = [n for n in names if n in business]
        absent = [n for n in names if n in orm_tables and n not in business]
        line = f"  [{group}] {len(present)}/{len(names)} 就位"
        if absent:
            line += f"   <== 缺 {', '.join(absent)}"
        print(line)

    conn.close()
    print()
    if ok and not extra_in_db:
        print(f"结构检查通过：ORM 模型与数据库完全一致（{len(business)} 张业务表）。")
        return 0
    if ok:
        print("结构检查通过（有数据库多余表，见上方提示）。")
        return 0
    print("结构检查未通过，请按上方指引处理。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

