"""删除改造前的旧界面截图与对应的早期截图脚本（经确认）。

只删这两类，别的都不动：
    1) docs/screenshots/fe-*.png —— 16 张，10-10 改造前的旧界面
    2) scripts/e2e_shot.js ~ e2e_shot7.js —— 7 个产出上面那批的早期脚本

保留：
    - e2e_shot8~12.js（产出 unit-*/ledger-*/wb-*/input-*/app-* 这批当前截图）
    - cdp.js（被所有脚本共用）
    - render_report.js
    - 其余 9 张当前截图

用法：
    .venv\\Scripts\\python.exe scripts/cleanup_legacy.py --dry-run
    .venv\\Scripts\\python.exe scripts/cleanup_legacy.py --apply
"""
from __future__ import annotations

import argparse
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND.parent

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()
DRY = not args.apply

print("=" * 70)
print(f"删除改造前的旧截图与早期脚本 —— {'演练（不删）' if DRY else '**实际删除**'}")
print("=" * 70)

targets: list[Path] = []

# 1. 旧界面截图
shots_dir = APP / "docs" / "screenshots"
old_shots = sorted(shots_dir.glob("fe-*.png"))
targets += old_shots

# 2. 早期截图脚本（e2e_shot.js 无编号，加上 2~7）
scripts_dir = APP / "scripts"
old_scripts = [scripts_dir / "e2e_shot.js"] + [
    scripts_dir / f"e2e_shot{i}.js" for i in range(2, 8)
]
targets += [p for p in old_scripts if p.exists()]

print(f"\n待删 {len(targets)} 个文件：\n")
total = 0
for p in targets:
    sz = p.stat().st_size
    total += sz
    tag = "[演练]" if DRY else "[删除]"
    print(f"  {tag} {p.relative_to(APP)}  ({sz / 1024:.0f} KB)")

if not DRY:
    for p in targets:
        p.unlink()

# 保留清单，让人放心
print("\n保留（当前在用）：")
for pat in ("unit-*.png", "ledger-*.png", "wb-*.png", "input-*.png", "app-*.png"):
    for p in sorted(shots_dir.glob(pat)):
        print(f"  ✓ {p.relative_to(APP)}")
for p in sorted(scripts_dir.glob("e2e_shot*.js")):
    print(f"  ✓ {p.relative_to(APP)}")
for name in ("cdp.js", "render_report.js"):
    p = scripts_dir / name
    if p.exists():
        print(f"  ✓ {p.relative_to(APP)}")

print("\n" + "=" * 70)
verb = "将释放" if DRY else "已释放"
print(f"{verb} {total / 1024 / 1024:.2f} MB")
if DRY:
    print("确认无误后加 --apply 执行")
print("=" * 70)
