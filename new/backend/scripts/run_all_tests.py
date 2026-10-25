"""运行全部测试。

**为什么需要这个脚本**：
各测试套件会修改共享状态（交付测试会锁定设计输入、状态机测试会发布版本、
变更测试会创建变更单）。如果直接依次跑而不重置数据库，
后跑的套件会因为前置状态被改掉而失败 —— 单独跑能过、合起来跑就挂，
这种问题最难排查。

所以本脚本在**每个套件之前**重置演示数据，保证每个套件都从确定的起点开始。
这也顺带保证了演示数据最终是干净的。

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/run_all_tests.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

SUITES = [
    ("smoke_test.py", "认证 / 权限 / 项目 / 字典"),
    ("test_admin_console.py", "系统管理控制台 / 创建账号 / 分配权限 / 重置密码"),
    ("test_unit_admin.py", "部门管理员 / 本部门账号 / 项目授权 / 离职停用"),
    ("test_employee_admin.py", "员工唯一性 / 批量入职停用 / 首次改密 / 生命周期"),
    ("test_profile.py", "个人设置 / 资料修改 / 密码修改"),
    ("test_merge_features.py", "合并版：88 项清单 / 工作台新建编辑项目 / 7 阶段自动创建"),
    ("test_version_rules.py", "版本状态机铁律 / 两级签认 / 参数溯源 / STALE"),
    ("test_change_impact.py", "变更六类影响 / 关闭互锁 / 权限边界"),
    ("test_issues.py", "问题八段链路 / 闭环互锁 / 知识沉淀"),
    ("test_deliverables.py", "成果清单 / 交付六道关卡 / 交付清单"),
    ("test_ai.py", "AI 治理规则 / 检索权限隔离 / 引用溯源"),
    ("test_ledger.py", "文档台账 / 责任落点 / 谁上传谁签认 / 文件在谁手上"),
    ("test_workbench.py", "工作台 / 跨项目待办 / 被退回 / 交办事项"),
    ("test_download.py", "演示文件下载 / 存储落盘一致性"),
    ("verify_objective.py", "★ 目标验收：换主体 / 阶段页 / 追溯 / 收尾 逐项核查"),
]


def run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(
        [str(PYTHON), *args],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    print("=" * 68)
    print("桩基工程全生命周期管理平台 —— 全量测试")
    print("=" * 68)

    total_pass = 0
    total_fail = 0
    failed_suites: list[str] = []

    for script, desc in SUITES:
        print(f"\n>>> 重置演示数据 ...")
        rc, out = run(["-m", "app.seed.seed_all", "--reset"])
        if rc != 0 or "种子数据写入完成" not in out:
            print(f"    重置失败！\n{out[-800:]}")
            return 1

        print(f">>> {script} —— {desc}")
        rc, out = run([f"scripts/{script}"])
        m = re.search(r"通过 (\d+) 项，失败 (\d+) 项", out)
        if not m:
            print(f"    无法解析结果（退出码 {rc}）")
            print("\n".join(out.strip().splitlines()[-15:]))
            failed_suites.append(script)
            total_fail += 1
            continue

        p, f = int(m.group(1)), int(m.group(2))
        total_pass += p
        total_fail += f
        flag = "OK" if f == 0 else "有失败"
        print(f"    通过 {p:3}  失败 {f}   [{flag}]")
        if f:
            failed_suites.append(script)
            for line in out.splitlines():
                if "[FAIL]" in line:
                    print(f"      {line.strip()}")

    # 最后再重置一次，保证交付给演示的数据是干净的
    print(f"\n>>> 恢复干净演示数据 ...")
    run(["-m", "app.seed.seed_all", "--reset"])

    print("\n" + "=" * 68)
    print(f"合计：通过 {total_pass} 项，失败 {total_fail} 项")
    if failed_suites:
        print(f"失败的套件：{', '.join(failed_suites)}")
    print("=" * 68)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
