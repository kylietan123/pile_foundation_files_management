"""遍历 app 目录，找出重复文件与疑似无用文件。

只做**只读扫描**，不删任何东西 —— 输出一份清单供人确认。
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parent.parent.parent

#: 不扫的目录（依赖/虚拟环境/版本库/缓存）
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".vite", ".pytest_cache"}

#: 跳过的小文件阈值（缓存类通常很小，单独处理）
def skip(p: Path) -> bool:
    return any(part in SKIP_DIRS for part in p.parts)


def sha(p: Path, limit: int = 0) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(1024 * 256)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


print("=" * 74)
print("app 目录扫描：重复文件 / 无用文件")
print("=" * 74)

files = [p for p in APP.rglob("*") if p.is_file() and not skip(p)]
print(f"\n待分析文件数（已排除 .git / node_modules / .venv / 缓存）：{len(files)}")

# ---------------- 1. 完全重复（内容相同）----------------
print("\n" + "-" * 74)
print("[1] 内容完全相同的文件组")
print("-" * 74)
by_hash: dict[str, list[Path]] = defaultdict(list)
for p in files:
    try:
        by_hash[sha(p)].append(p)
    except OSError:
        pass

dupes = {h: ps for h, ps in by_hash.items() if len(ps) > 1}
if not dupes:
    print("  没有内容完全相同的文件")
tot_waste = 0
for h, ps in sorted(dupes.items(), key=lambda kv: -kv[1][0].stat().st_size):
    sz = ps[0].stat().st_size
    waste = sz * (len(ps) - 1)
    tot_waste += waste
    print(f"\n  重复 {len(ps)} 份，每份 {sz / 1024:.1f} KB，可省 {waste / 1024:.1f} KB")
    for p in ps:
        print(f"    {p.relative_to(APP)}")
print(f"\n  重复可省合计：{tot_waste / 1024 / 1024:.2f} MB")

# ---------------- 2. 空文件 / 极小的垃圾文件 ----------------
print("\n" + "-" * 74)
print("[2] 空文件（0 字节）")
print("-" * 74)
empties = [p for p in files if p.stat().st_size == 0]
if empties:
    for p in empties:
        print(f"  {p.relative_to(APP)}")
else:
    print("  无")

# ---------------- 3. 临时/探针脚本残留 ----------------
print("\n" + "-" * 74)
print("[3] 临时脚本残留（_fix / _probe / _tmp / ~ 等命名习惯）")
print("-" * 74)
junk_pat = re.compile(r"(^_|^tmp_|_tmp\.|\.bak$|\.orig$|\.old$|~$|\.swp$|\.tmp$)")
junk = [p for p in files if junk_pat.search(p.name)]
if junk:
    for p in junk:
        print(f"  {p.relative_to(APP)}  ({p.stat().st_size} 字节)")
else:
    print("  无")

# ---------------- 4. Python 缓存 ----------------
print("\n" + "-" * 74)
print("[4] Python 缓存目录 __pycache__")
print("-" * 74)
caches = [p for p in APP.rglob("__pycache__") if p.is_dir()]
n_pyc = sum(1 for c in caches for _ in c.glob("*.pyc"))
print(f"  目录数：{len(caches)}   文件数：{n_pyc}")
print("  （已被 .gitignore 忽略，删掉不影响运行，但会自动重新生成）")

# ---------------- 5. 脚本是否被引用 ----------------
print("\n" + "-" * 74)
print("[5] scripts/ 下的脚本：是否被别处引用")
print("-" * 74)
scripts = sorted((APP / "backend" / "scripts").glob("*.py")) + \
          sorted((APP / "scripts").glob("*.js"))
# 收集所有 py/js/vue/ts/md 的文本用于查找引用
texts: dict[Path, str] = {}
for p in files:
    if p.suffix in (".py", ".js", ".ts", ".vue", ".md", ".txt", ".json"):
        try:
            texts[p] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

for s in scripts:
    refs = []
    for p, t in texts.items():
        if p == s:
            continue
        if s.name in t:
            refs.append(p.relative_to(APP))
    mark = "★" if refs else "?"
    print(f"  {mark} {s.relative_to(APP)}  ← 被 {len(refs)} 处提到")
    if refs and len(refs) <= 4:
        for r in refs:
            print(f"        {r}")

# ---------------- 6. 截图是否被文档引用 ----------------
print("\n" + "-" * 74)
print("[6] docs/ 下的图片：是否被任何文档引用")
print("-" * 74)
imgs = sorted((APP / "docs").rglob("*.png"))
doc_texts = {p: t for p, t in texts.items() if p.suffix in (".md", ".html", ".txt")}
unref = []
for img in imgs:
    rel = img.relative_to(APP).as_posix()
    hit = any(rel in t or img.name in t for t in doc_texts.values())
    if not hit:
        unref.append(img)
print(f"  图片总数：{len(imgs)}   未被引用：{len(unref)}")
for p in unref:
    print(f"    {p.relative_to(APP)}  ({p.stat().st_size / 1024:.0f} KB)")
