"""打一个可以发给队友的源码包。

为什么不用 `git archive`：
    中文路径在 PowerShell 里会拿到 git 转义后的 `"d\346\226\207..."` 形式，
    拼不出真实路径。Python 直接读 git 的原始输出（关闭 quotepath），
    路径一定正确。

产物分两个包：
    1) 源码包（默认）—— 队友开发要用的全部代码与文档，约 1.2 MB
    2) 预览包（--with-preview）—— 额外带汇报图与界面截图，约 30 MB

用法：
    .venv\\Scripts\\python.exe scripts\\make_dist.py <输出目录>
    .venv\\Scripts\\python.exe scripts\\make_dist.py <输出目录> --with-preview
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR.parent

#: 预览用的大图，默认不进源码包（队友开发用不到）
PREVIEW_PREFIXES = ("docs/screenshots/", "docs/report-diagrams/render/")


def git(*args: str) -> str:
    """执行 git 命令，强制关闭路径转义，拿到可用的 UTF-8 路径。"""
    p = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(APP_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if p.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失败：{p.stderr[:400]}")
    return p.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description="打一个发给队友的源码包")
    ap.add_argument("outdir", help="输出目录")
    ap.add_argument("--with-preview", action="store_true",
                    help="额外打包汇报图与界面截图（约 30 MB）")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    files = [f for f in git("ls-files").splitlines() if f.strip()]
    if not args.with_preview:
        files = [f for f in files if not f.startswith(PREVIEW_PREFIXES)]

    # 工作区不能有未提交改动，否则包里会是"旧代码 + 新提交信息"不一致
    dirty = git("status", "--porcelain").strip()
    if dirty:
        print("提示：工作区有未提交改动，包里只含**已提交**的内容：")
        for line in dirty.splitlines()[:10]:
            print(f"    {line}")
        print()

    head = git("log", "-1", "--format=%h %ad %s", "--date=short").strip()
    stamp = datetime.now().strftime("%Y%m%d")

    name = f"pile-lcm-源码-{stamp}.zip" if not args.with_preview else f"pile-lcm-全量含预览-{stamp}.zip"
    target = outdir / name

    missing: list[str] = []
    total = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            src = APP_DIR / f
            if not src.is_file():
                missing.append(f)
                continue
            z.write(src, arcname=f"pile-lcm/{f}")
            total += src.stat().st_size

        # 附一张说明卡，队友解压第一眼就看到
        z.writestr(
            "pile-lcm/【先看这个】版本说明.txt",
            f"""桩基工程全生命周期管理平台 —— 源码包

打包时间 ：{datetime.now().strftime('%Y-%m-%d %H:%M')}
版本     ：{head}
文件数   ：{len(files) - len(missing)}

============================================================
怎么开始（详细步骤见 协作入门.md）
============================================================

1. 解压到一个**纯英文、无空格**的路径，例如：
       D:\\work\\pile-lcm
   （中文路径 + 空格容易在 Python/Node 各种环节出问题）

2. 装后端（第一次约 5 分钟）
       cd backend
       python -m venv .venv
       .venv\\Scripts\\python.exe -m pip install -r requirements.lock.txt
       .venv\\Scripts\\python.exe -m alembic upgrade head
       .venv\\Scripts\\python.exe -m app.seed.seed_all --reset
       .venv\\Scripts\\python.exe scripts\\check_db.py

3. 装前端
       cd ..\\frontend
       npm install

4. 起服务（开两个终端）
       后端： cd backend
              .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000
       前端： cd frontend
              npm run dev

5. 浏览器打开 http://127.0.0.1:5173/
   演示账号密码统一：Tjad@2026
   建议对比 ouyuxin（设计单位）与 wangwu（监理单位）看权限差异

6. 确认环境没问题：跑一遍全量测试（564 项应全过）
       cd backend
       .venv\\Scripts\\python.exe scripts\\run_all_tests.py

============================================================
这个包里没有 node_modules 和 .venv（共约 250 MB），
请按上面第 2、3 步自己装 —— 这也是必须的，换机器不能直接拷。
============================================================

改完代码怎么发回来：见 docs\\改动汇总流程.md
""",
        )

    size = target.stat().st_size
    print(f"已生成：{target}")
    print(f"  文件数   ：{len(files) - len(missing)}")
    print(f"  解压后体积：{total / 1024 / 1024:.2f} MB")
    print(f"  压缩包体积：{size / 1024 / 1024:.2f} MB")
    print(f"  版本     ：{head}")
    if missing:
        print(f"  缺失（已跳过）：{missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
