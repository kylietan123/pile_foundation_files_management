"""核对 storage/ 与 file_object 表是否一致 —— 找出孤儿文件。"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.document import FileObject  # noqa: E402

root = Path(settings.STORAGE_ROOT)
print(f"STORAGE_ROOT = {root}")
print(f"存在     = {root.exists()}\n")

db = SessionLocal()
try:
    objs = db.execute(select(FileObject)).scalars().all()
    print(f"file_object 表记录：{len(objs)} 个")
    for o in objs:
        p = root / o.storage_key
        ok = "✓" if p.exists() else "✗ 文件缺失"
        print(f"  {ok}  {o.file_id[:16]}...  size={o.size}  ref={o.ref_count}  {o.original_name}")

    recorded = {o.file_id for o in objs}
    recorded_keys = {o.storage_key for o in objs}
finally:
    db.close()

print()
disk = [p for p in root.rglob("*") if p.is_file()] if root.exists() else []
print(f"storage/ 磁盘上的文件：{len(disk)} 个")
orphans = []
for p in disk:
    key = p.relative_to(root).as_posix()
    if key not in recorded_keys:
        orphans.append((key, p.stat().st_size))

if orphans:
    print(f"\n**孤儿文件（磁盘上有、数据库没有记录）{len(orphans)} 个：**")
    for k, sz in orphans:
        print(f"  {k}  {sz} 字节")
else:
    print("没有孤儿文件")

missing = [o for o in recorded if o not in {p.stem for p in disk}]
print(f"\n数据库有记录但磁盘无文件：{len(missing)} 个")
