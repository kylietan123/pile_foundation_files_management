"""量化"队友改自己模块时，会碰到多少公共层"。

结论用来回答一个具体问题：三个人并行开发，冲突面到底有多大。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parent.parent.parent

#: 公共层（不能各自改）
CORE = [
    "backend/app/models/enums.py",
    "backend/app/models/base.py",
    "backend/app/core/permissions.py",
    "backend/app/core/security.py",
    "backend/app/core/database.py",
    "backend/app/services/documents.py",
    "backend/app/services/workflow.py",
    "backend/app/services/storage.py",
    "backend/app/api/deps.py",
]

#: 只能"追加"的注册点
APPEND_ONLY = [
    "backend/app/main.py",
    "backend/app/models/__init__.py",
    "backend/app/schemas.py",
    "frontend/src/api/types.ts",
    "frontend/src/api/index.ts",
    "frontend/src/router/index.ts",
]


def git(*args: str) -> str:
    p = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                       cwd=str(APP), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.stdout


print("=" * 70)
print("并行开发冲突面分析")
print("=" * 70)

# ---- 1. 公共层的"变动频次"：越常改越容易撞 ----
print("\n[1] 公共层最近 20 次提交里被改了几次（越常改越危险）")
recent = git("log", "-20", "--name-only", "--format=").splitlines()
from collections import Counter
cnt = Counter(f.strip() for f in recent if f.strip())
for c in CORE:
    print(f"  {c.split('/')[-1]:22} {cnt.get(c, 0):2} 次")

# ---- 2. 追加型注册点：三方都要碰，但只加行 ----
print("\n[2] 只能追加的注册点（三个人都要碰，但只加行不撞车）")
for f in APPEND_ONLY:
    p = APP / f
    if p.exists():
        n = len(p.read_text(encoding="utf-8").splitlines())
        print(f"  {f:38} {n:4} 行")

# ---- 3. 判定：阶段模块能不能完全不建表 ----
print("\n[3] 关键判断：阶段模块是否必须新建表")
tables = ["document", "document_version", "file_object",
          "workflow_instance", "workflow_task", "audit_log"]
print("  平台已有的通用能力表：")
for t in tables:
    print(f"    {t}")
print("""
  → 如果队友的阶段模块只是"管文件"（上传/台账/签认/追溯），
    **这些表已经够了，一行数据库迁移都不用加**。
    那就完全没有迁移链冲突。

  → 只有当他需要**该阶段专有的结构化数据**时才要建表
    （例如勘察的钻孔记录、土工试验值），这时才需要迁移，
    而迁移是链式的、必须串行。
""")

# ---- 4. 当前迁移链 ----
vers = sorted((APP / "backend" / "migrations" / "versions").glob("*.py"))
print(f"[4] 当前迁移文件数：{len(vers)}")
for v in vers:
    print(f"  {v.name}")
print("""
  → 每条迁移记着 down_revision 指向谁，是**一条链**。
    三个人各自生成 → 多个 head → 必须 merge，且容易顺序错。
    所以迁移只能由一个人（欧雨欣）在合并后统一生成。
""")
