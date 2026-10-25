"""演示数据健康检查。

用途：跑完测试后确认演示数据是否干净（没有测试残留、参数状态正常）。
如果发现残留，执行 `python -m app.seed.seed_all --reset` 恢复。

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/check_demo_data.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402

# 期望值（与 app/seed/ 一致）
EXPECT = {
    "document": 5,
    "project": 4,
    # 用户从 6 人扩到 12 人：新模型要覆盖 11 个参与单位 + 系统管理员
    "app_user": 12,
    "design_param": 19,
    # 单位类型字典从 8 项改为 11 项（按《管理流程》的参与单位）
    "dict_item": 65,
}


def main() -> int:
    if not settings.DATABASE_URL.startswith("sqlite"):
        print("当前不是 SQLite，跳过本地检查")
        return 0

    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    if not Path(db_path).exists():
        print("数据库不存在，请先执行 aiembic upgrade head 与 seed_all")
        return 1

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    problems: list[str] = []

    print(f"数据库：{db_path}\n")

    for table, expected in EXPECT.items():
        n = cur.execute(f"select count(*) from {table}").fetchone()[0]
        ok = n == expected
        print(f"  {table:<16} {n:>4}  (期望 {expected})  {'OK' if ok else '<== 不一致'}")
        if not ok:
            problems.append(f"{table} 数量为 {n}，期望 {expected}")

    print()

    # 测试残留
    leftover = cur.execute(
        "select count(*) from document where doc_no like 'TEST-%'"
    ).fetchone()[0]
    print(f"  测试文档残留      {leftover:>4}  (期望 0)")
    if leftover:
        problems.append(f"存在 {leftover} 份 TEST-* 测试文档")

    # 文件落盘一致性 —— 这一项曾经缺失，导致一个真实 bug 长期没被发现：
    # 种子只写 file_object 记录、不写磁盘，且自编的 storage_key 与
    # storage.read_bytes() 的查找规则不一致，演示文件的**下载一律 404**。
    # 光看数据库行数是对的，所以之前的检查全过。
    print()
    fids = [r[0] for r in cur.execute("select file_id from file_object").fetchall()]
    root = Path(settings.STORAGE_ROOT)
    missing_files: list[str] = []
    for fid in fids:
        d = root / fid[:2] / fid[2:4]
        if not d.exists() or not list(d.glob(f"{fid}.*")):
            missing_files.append(fid)
    disk_total = len([p for p in root.rglob("*") if p.is_file()]) if root.exists() else 0
    print(f"  file_object 记录   {len(fids):>4}")
    print(f"  storage 实际文件   {disk_total:>4}")
    print(f"  记录存在但文件缺失 {len(missing_files):>4}  (期望 0)")
    if missing_files:
        problems.append(
            f"{len(missing_files)} 个 file_object 在 storage/ 里没有对应文件，"
            f"下载会 404（例如 {missing_files[0][:16]}…）。"
            f"若是种子问题，检查 app/seed/seed_content.py 的 _make_file 是否真的落盘"
        )
    orphans = max(0, disk_total - (len(fids) - len(missing_files)))
    print(f"  孤儿文件（无记录） {orphans:>4}  (期望 0)")
    if orphans:
        problems.append(f"storage/ 有 {orphans} 个孤儿文件（数据库无记录），可清理")

    # 参数状态
    rows = cur.execute(
        "select verify_status, count(*) from design_param group by verify_status"
    ).fetchall()
    print(f"\n  设计参数核验状态：{dict(rows)}")

    locked = cur.execute("select count(*) from design_param where locked = 1").fetchone()[0]
    print(f"  已锁定参数        {locked:>4}  (期望 0)")
    if locked:
        problems.append(f"有 {locked} 项参数处于锁定状态")

    # 已发布版本数：每个文件最多一个
    multi = cur.execute(
        """
        select document_id, count(*) c from document_version
        where state = 'PUBLISHED' group by document_id having c > 1
        """
    ).fetchall()
    print(f"  违反「最多一个已发布版本」的文件：{len(multi)}")
    if multi:
        problems.append(f"{len(multi)} 个文件存在多个已发布版本（违反铁律 4）")

    # 审批中的版本
    inflight = cur.execute(
        """
        select document_id, count(*) c from document_version
        where state in ('CHECKING','REVIEWING','APPROVED')
        group by document_id having c > 1
        """
    ).fetchall()
    print(f"  违反「最多一个审批中版本」的文件：{len(inflight)}")
    if inflight:
        problems.append(f"{len(inflight)} 个文件存在多个审批中版本（违反铁律 2）")

    # ---------- 变更单与桩位数据是否自洽 ----------
    # 演示数据的数量必须对得上，否则"受影响桩位清单"列出的数量与汇总不符，
    # 一眼就能看出是假数据。
    print()
    zones = dict(cur.execute("select zone, count(*) from pile group by zone").fetchall())
    print(f"  桩位分区分布：{zones}")

    changes = cur.execute(
        """
        select change_no, impact_pile_count, impact_constructed_count, impact_scope
        from change_request order by change_no
        """
    ).fetchall()
    print()
    for no, pile_cnt, cons_cnt, scope_json in changes:
        scope_zones: list[str] = []
        if scope_json:
            try:
                scope_zones = json.loads(scope_json).get("zones") or []
            except (ValueError, AttributeError):
                scope_zones = []

        # 该变更声明的分区内实际有多少桩、其中多少已施工
        actual_total = sum(zones.get(z, 0) for z in scope_zones)
        actual_cons = 0
        if scope_zones:
            placeholders = ",".join("?" for _ in scope_zones)
            actual_cons = cur.execute(
                f"select count(*) from pile where zone in ({placeholders}) "
                f"and status in ('CONSTRUCTED','ACCEPTED')",
                scope_zones,
            ).fetchone()[0]

        ok = True
        detail = f"声明 {pile_cnt} 根 / 已施工 {cons_cnt} 根"
        if scope_zones and pile_cnt != actual_total:
            ok = False
            detail += f"  <== 与分区实际桩数 {actual_total} 不符"
        if scope_zones and cons_cnt != actual_cons:
            ok = False
            detail += f"  <== 与分区实际已施工 {actual_cons} 不符"
        if pile_cnt > 0 and not scope_zones:
            ok = False
            detail += "  <== 有桩位影响却没填分区，前端列不出明细"

        # 声明了已施工桩位，就必须有对应的「已施工部位」风险明细 ——
        # 否则会出现"汇总说 64 根已施工，明细里却没有对应风险项"的自相矛盾。
        if cons_cnt > 0:
            cp = cur.execute(
                "select count(*) from change_impact where change_id = "
                "(select id from change_request where change_no = ?) "
                "and target_type = 'CONSTRUCTED_PART'",
                (no,),
            ).fetchone()[0]
            if cp == 0:
                ok = False
                detail += "  <== 声明已施工桩位但明细里没有「已施工部位」风险项"

        print(f"  {no}  {detail}  {'OK' if ok else '<== 不一致'}")
        if not ok:
            problems.append(f"{no} 的桩位数量与分区实际数据不一致")

    # ---------- 变更状态与流程实例一致性 ----------
    # 踩过的坑：手写 state=PENDING_APPROVAL 但没有 workflow_instance，
    # 而这个状态是系统自身到达不了的（提交时会同时建流程），
    # 结果变更永远卡住、既无法提交也无法关闭。
    print()
    submitted_states = {"APPROVING", "APPROVED", "EXECUTING", "CLOSED"}
    bad_state = cur.execute(
        """
        select change_no, state, workflow_instance_id from change_request
        where state in ('APPROVING','APPROVED','EXECUTING','CLOSED')
          and (workflow_instance_id is null or workflow_instance_id = '')
        """
    ).fetchall()
    print(f"  已提交但缺流程实例的变更：{len(bad_state)}")
    for no, st, _ in bad_state:
        print(f"    {no} state={st}  <== 状态与流程不一致")
        problems.append(f"{no} 状态为 {st} 但没有流程实例，变更会卡死无法关闭")

    # 反向：有流程实例但状态还是待提交
    reverse_bad = cur.execute(
        """
        select change_no, state from change_request
        where state in ('DRAFT','IMPACT_ANALYZING')
          and workflow_instance_id is not null and workflow_instance_id != ''
        """
    ).fetchall()
    print(f"  有流程但状态仍为待提交的变更：{len(reverse_bad)}")
    for no, st in reverse_bad:
        print(f"    {no} state={st}  <== 状态与流程不一致")
        problems.append(f"{no} 有流程实例但状态为 {st}")

    # ---------- 问题链路进度与状态一致性 ----------
    # 已闭环的问题必须有验证环节（否则闭环走了形式）
    print()
    closed_no_verify = cur.execute(
        """
        select i.issue_no, i.title from issue i
        where i.status = 'CLOSED'
          and not exists (
            select 1 from issue_action a
            where a.issue_id = i.id and a.action_type = 'VERIFY'
          )
        """
    ).fetchall()
    print(f"  已闭环但缺「验证」环节的问题：{len(closed_no_verify)}")
    for no, title in closed_no_verify:
        print(f"    {no} {title[:24]}  <== 闭环缺少验证")
        problems.append(f"{no} 已闭环但没有验证环节（闭环走了形式）")

    conn.close()

    print()
    if problems:
        print("发现 %d 个问题：" % len(problems))
        for p in problems:
            print(f"  - {p}")
        print("\n恢复干净演示数据：")
        print("  .venv\\Scripts\\python.exe -m app.seed.seed_all --reset")
        return 1

    print("演示数据检查通过：干净、状态正常。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
