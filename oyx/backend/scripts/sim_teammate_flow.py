"""模拟队友侧完整流程，验证「源码包 + patch」这条路真的走得通。

做的事：
    1) 解压源码包到临时目录
    2) git init + 首次提交（记下起点）
    3) 模拟队友加一个小功能（复用现有表，不碰迁移）
    4) 导出 patch
    5) 回到主仓库 git apply --check 验证能打上
    6) 真的 apply 上去，跑一次测试，再回滚

**这个脚本本身就是验收** —— 文档写的流程如果跑不通，这里会失败。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent.parent
ZIP = next(iter(sorted((APP_DIR.parent / "发给队友").glob("pile-lcm-源码-*.zip"))), None)

if ZIP is None:
    raise SystemExit("找不到源码包，先跑 make_dist.py")

print(f"源码包：{ZIP.name}  ({ZIP.stat().st_size / 1024:.0f} KB)")

work = Path(tempfile.mkdtemp(prefix="teammate-sim-"))
print(f"模拟队友目录：{work}\n")


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        print(f"  命令失败：{' '.join(cmd)}")
        print(f"  stdout: {p.stdout[-600:]}")
        print(f"  stderr: {p.stderr[-600:]}")
        raise SystemExit(1)
    return p


ok = 0
bad = 0


def chk(desc: str, cond: bool, extra: str = "") -> None:
    global ok, bad
    if cond:
        ok += 1
        print(f"  [OK]   {desc}")
    else:
        bad += 1
        print(f"  [FAIL] {desc}  {extra}")


try:
    # ---------- 1. 解压 ----------
    print("[1] 解压源码包")
    with zipfile.ZipFile(ZIP) as z:
        names = z.namelist()
        z.extractall(work)
    chk("解压出 pile-lcm/ 顶层目录", any(n.startswith("pile-lcm/") for n in names))
    chk("带【先看这个】说明文件",
        any("先看这个" in n for n in names), str([n for n in names if "说明" in n]))
    proj = work / "pile-lcm"
    chk("关键文件都在",
        (proj / "README.md").is_file()
        and (proj / "协作入门.md").is_file()
        and (proj / "backend" / "app" / "main.py").is_file()
        and (proj / "docs" / "改动汇总流程.md").is_file())
    chk("没有 node_modules（应自己装）", not (proj / "frontend" / "node_modules").exists())
    chk("没有 .venv（应自己建）", not (proj / "backend" / ".venv").exists())
    chk("没有带 .git（队友自己 init）", not (proj / ".git").exists())

    # ---------- 2. git init ----------
    print("\n[2] 队友侧 git init")
    run(["git", "init", "-q"], proj)
    run(["git", "config", "user.email", "teammate@test"], proj)
    run(["git", "config", "user.name", "队友模拟"], proj)
    run(["git", "add", "-A"], proj)
    run(["git", "commit", "-q", "-m", "从欧雨欣的源码包初始化"], proj)
    base = run(["git", "rev-parse", "HEAD"], proj).stdout.strip()
    chk("首次提交成功，拿到起点提交号", len(base) == 40, base)

    # ---------- 3. 模拟加一个小功能 ----------
    print("\n[3] 模拟队友加功能（复用现有表，不碰迁移）")
    svc = proj / "backend" / "app" / "services" / "survey.py"
    svc.write_text(
        '''"""勘察阶段业务规则（队友模拟新增）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import SoilLayer


def list_layers(db: Session, project_id: str) -> list[dict]:
    """列出某项目的土层 —— 复用公共层的 project 归属，不新建表。"""
    rows = db.execute(
        select(SoilLayer).where(SoilLayer.project_id == project_id).order_by(SoilLayer.layer_no)
    ).scalars().all()
    return [
        {"id": r.id, "layer_no": r.layer_no, "name": r.name, "depth_top": r.depth_top}
        for r in rows
    ]
''',
        encoding="utf-8",
    )
    run(["git", "add", "-A"], proj)
    run(["git", "commit", "-q", "-m", "feat(survey): 新增土层列表 service"], proj)
    chk("队友侧生成新文件", svc.is_file())

    # ---------- 4. 导出 patch ----------
    print("\n[4] 导出 patch")
    patch = work / "survey-teammate.patch"
    out = run(["git", "format-patch", base, "--stdout"], proj).stdout
    patch.write_text(out, encoding="utf-8")
    chk("patch 已生成且非空", patch.stat().st_size > 200, f"{patch.stat().st_size} 字节")
    chk("patch 里含提交信息", "feat(survey)" in out)
    print(f"       patch 体积：{patch.stat().st_size} 字节")

    # ---------- 5. 主仓库验证能打上 ----------
    print("\n[5] 主仓库验证 patch 能应用")
    chk("主仓库当前没有该文件（确认是新增）",
        not (APP_DIR / "backend" / "app" / "services" / "survey.py").exists())
    r = run(["git", "apply", "--check", str(patch)], APP_DIR, check=False)
    chk("git apply --check 通过", r.returncode == 0, r.stderr[-400:])

    # ---------- 6. 真的应用 + 验证 + 回滚 ----------
    print("\n[6] 真正应用 patch 并验证")
    r = run(["git", "apply", str(patch)], APP_DIR, check=False)
    chk("git apply 成功", r.returncode == 0, r.stderr[-400:])
    applied = APP_DIR / "backend" / "app" / "services" / "survey.py"
    chk("文件已落到主仓库", applied.is_file())

    if applied.is_file():
        # 导入能不能过（说明 patch 出来的代码语法没问题）
        r = run([sys.executable, "-c",
                 "import sys; sys.path.insert(0,'.'); "
                 "from app.services import survey; print('导入 OK')"],
                APP_DIR / "backend", check=False)
        chk("应用后的代码能正常导入", "导入 OK" in r.stdout, (r.stdout + r.stderr)[-400:])

    # 回滚：把 patch 带来的改动清掉（模拟"合并前先验证"）
    run(["git", "checkout", "--", "."], APP_DIR, check=False)
    if applied.exists():
        applied.unlink()
    r = run(["git", "status", "--porcelain"], APP_DIR)
    chk("回滚后工作区干净", not r.stdout.strip(), r.stdout[:300])

    print("\n" + "=" * 62)
    print(f"队友流程实测：{ok} 项通过，{bad} 项未通过")
    print("=" * 62)
finally:
    shutil.rmtree(work, ignore_errors=True)

sys.exit(0 if bad == 0 else 1)
