"""清理 app 目录中确认无用的文件。

**只清理已确认为垃圾的东西**，不碰任何有争议的内容：
    1) 0 字节的残留文件
    2) storage/ 里的孤儿文件（磁盘有、数据库无记录）
    3) __pycache__ 缓存

有争议的（旧截图、旧 e2e 脚本）**不动**，只列出报告。

用法：
    .venv\\Scripts\\python.exe scripts/cleanup_app.py --dry-run   # 只看
    .venv\\Scripts\\python.exe scripts/cleanup_app.py --apply     # 真删
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.document import FileObject  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true", help="真正删除（默认只演练）")
args = ap.parse_args()
DRY = not args.apply

print("=" * 72)
print(f"清理 app 目录 —— {'演练模式（不删任何东西）' if DRY else '**实际删除**'}")
print("=" * 72)

removed_files = 0
removed_bytes = 0


def kill(p: Path, reason: str) -> None:
    global removed_files, removed_bytes
    sz = p.stat().st_size if p.exists() and p.is_file() else 0
    tag = "[演练]" if DRY else "[删除]"
    print(f"  {tag} {p.relative_to(APP)}  ({sz} 字节)  ← {reason}")
    if not DRY:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
    removed_files += 1
    removed_bytes += sz


# ---------------- 1. 0 字节残留文件 ----------------
print("\n[1] 0 字节的残留文件")
zero = [
    APP / "backend" / "pile_lcm.db",   # 空库，真正的库在 app/pile_lcm.db
]
for p in zero:
    if p.exists() and p.is_file() and p.stat().st_size == 0:
        kill(p, "0 字节的空数据库（真正的库在 app/pile_lcm.db）")
    else:
        print(f"  [跳过] {p.relative_to(APP)}（不存在或非空）")

# ---------------- 2. storage 孤儿文件 ----------------
print("\n[2] storage/ 孤儿文件（磁盘有、数据库无记录）")
root = Path(settings.STORAGE_ROOT)
db = SessionLocal()
try:
    recorded = {
        o.storage_key for o in db.execute(select(FileObject)).scalars().all()
    }
finally:
    db.close()

if not root.exists():
    print(f"  storage 目录不存在：{root}")
else:
    orphans = [
        p for p in root.rglob("*")
        if p.is_file() and p.relative_to(root).as_posix() not in recorded
    ]
    if orphans:
        for p in sorted(orphans):
            kill(p, "数据库中无对应 file_object 记录")
    else:
        print("  没有孤儿文件")

# ---------------- 3. __pycache__ ----------------
print("\n[3] Python 缓存 __pycache__")
caches = [p for p in APP.rglob("__pycache__") if p.is_dir()
          and ".venv" not in p.parts]
n_pyc = sum(1 for c in caches for _ in c.rglob("*.pyc"))
print(f"  目录 {len(caches)} 个，.pyc 文件 {n_pyc} 个")
if caches and not DRY:
    for c in caches:
        shutil.rmtree(c, ignore_errors=True)
    print("  已全部删除（下次运行会自动重建，不影响功能）")
elif caches:
    print("  [演练] 将全部删除")

# ---------------- 4. 报告：有争议的，不动 ----------------
print("\n[4] 以下**有争议，本次不动**，请你决定")
shots = sorted((APP / "docs" / "screenshots").glob("fe-*.png"))
old_shots_sz = sum(p.stat().st_size for p in shots)
print(f"\n  (a) 旧界面截图 {len(shots)} 张，共 {old_shots_sz / 1024 / 1024:.2f} MB")
print("      时间 10-10，**改造前**的界面（还是旧的岗位角色模型）")
print("      现在已与实际界面不一致：")
for p in shots[:4]:
    print(f"        {p.name}")
print("        …")
print("      注：README 与其它文档**并未引用**这些图，只在历史对话里用过")
print("      风险：全是史料。删了就再也看不到改造前的样子")

old_scripts = sorted((APP / "scripts").glob("e2e_shot[1-7].js"))
print(f"\n  (b) 早期 e2e 截图脚本 {len(old_scripts)} 个")
for p in old_scripts:
    print(f"        {p.name}  {p.stat().st_size / 1024:.1f} KB")
print("      10-10 写的，产出上面那批旧截图；改造后已不再使用")
print("      风险：极低（功能被 e2e_shot8~12 覆盖）")

print(f"\n  (c) 未被引用的脚本（功能有效，只是没人从文档里链过去）")
for name in ("analyze_coupling.py", "find_junk.py", "sim_teammate_flow.py",
             "check_storage.py"):
    p = BACKEND / "scripts" / name
    if p.exists():
        print(f"        backend/scripts/{name}")
print("      **建议保留**：这些是我这轮新加的分析/自检工具，有用")
print("      可选：把它们写进 README 的工具清单，就不会再显示'未被引用'")

# ---------------- 汇总 ----------------
print("\n" + "=" * 72)
if DRY:
    print(f"演练结果：将删除 {removed_files} 个文件，约 {removed_bytes / 1024:.1f} KB")
    print("确认无误后加 --apply 真正执行")
else:
    print(f"已删除 {removed_files} 个文件，释放约 {removed_bytes / 1024:.1f} KB")
    print(f"另有 __pycache__ {n_pyc} 个 .pyc 已清理")
print("=" * 72)
