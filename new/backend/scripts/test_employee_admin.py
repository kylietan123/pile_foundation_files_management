"""员工管理增强测试：唯一工号/邮箱、批量入职/停用、首次改密、生命周期字段。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.ai import AuditLog  # noqa: E402

PASSWORD = "Tjad@2026"
passed = 0
failed = 0


def check(desc: str, cond: bool, extra: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {desc}")
    else:
        failed += 1
        print(f"  [FAIL] {desc}  {extra}")


def login(client: TestClient, username: str, password: str):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def auth_headers(client: TestClient, username: str, password: str = PASSWORD) -> dict[str, str]:
    r = login(client, username, password)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def pool(client: TestClient, headers: dict[str, str], keyword: str) -> dict:
    rows = client.get("/api/v1/admin/users", headers=headers, params={"keyword": keyword}).json().get("data") or []
    return rows[0] if rows else {}


def main() -> int:
    client = TestClient(app)
    suffix = str(int(time.time()))
    admin_h = auth_headers(client, "admin")
    admin_opts = client.get("/api/v1/admin/options", headers=admin_h).json()["data"]
    owner_org = next(o for o in admin_opts["orgs"] if o["org_type"] == "OWNER")
    tjad_org = next(o for o in admin_opts["orgs"] if o["org_type"] == "DESIGN")

    a_username = f"emp_a_{suffix}"
    b_username = f"emp_b_{suffix}"
    c_username = f"emp_c_{suffix}"
    a_employee_no = f"E{suffix}"

    print("\n[1] 工号、邮箱唯一性与规范化")
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_h,
        json={
            "username": a_username,
            "password": "Initial@123",
            "name": "员工甲",
            "employee_no": a_employee_no.lower(),
            "email": f"EMP_{suffix}@Example.com",
            "org_id": owner_org["id"],
            "hire_date": "2026-10-01",
        },
    )
    check("创建员工甲成功", r.status_code == 201, r.text[:300])
    employee_a = r.json().get("data") or {}
    check("工号保存为大写规范值", employee_a.get("employee_no") == a_employee_no.upper())
    check("邮箱保存为小写规范值", employee_a.get("email") == f"emp_{suffix}@example.com")
    check("新员工标记为必须首次改密", employee_a.get("must_change_password") is True)

    r = client.post(
        "/api/v1/admin/users",
        headers=admin_h,
        json={
            "username": b_username,
            "password": "Initial@123",
            "name": "员工乙",
            "employee_no": a_employee_no.upper(),
            "email": f"emp_b_{suffix}@example.com",
            "org_id": owner_org["id"],
        },
    )
    check("重复工号被拒绝", r.status_code == 409, r.text[:300])

    r = client.post(
        "/api/v1/admin/users",
        headers=admin_h,
        json={
            "username": c_username,
            "password": "Initial@123",
            "name": "员工丙",
            "employee_no": f"F{suffix}",
            "email": f"EMP_{suffix}@EXAMPLE.COM",
            "org_id": owner_org["id"],
        },
    )
    check("重复邮箱（大小写不同）被拒绝", r.status_code == 409, r.text[:300])

    r = client.post(
        "/api/v1/admin/users",
        headers=admin_h,
        json={
            "username": b_username,
            "password": "Initial@123",
            "name": "员工乙",
            "employee_no": f"F{suffix}",
            "email": f"emp_b_{suffix}@example.com",
            "org_id": owner_org["id"],
        },
    )
    check("创建员工乙成功", r.status_code == 201, r.text[:300])
    employee_b = r.json().get("data") or {}
    r = client.patch(
        f"/api/v1/admin/users/{employee_b['id']}",
        headers=admin_h,
        json={"employee_no": a_employee_no.upper()},
    )
    check("修改为重复工号被拒绝", r.status_code == 409, r.text[:300])

    print("\n[2] 首次登录强制修改初始密码")
    r = login(client, a_username, "Initial@123")
    check("新员工可以使用初始密码登录", r.status_code == 200, r.text[:300])
    login_data = r.json().get("data") or {}
    check("登录响应提示必须改密", login_data.get("must_change_password") is True)
    initial_h = {"Authorization": f"Bearer {login_data['access_token']}"}
    check("改密前可以读取 /auth/me", client.get("/api/v1/auth/me", headers=initial_h).status_code == 200)
    r = client.get("/api/v1/projects", headers=initial_h)
    check("改密前不能进入业务接口", r.status_code == 403, r.text[:300])
    r = client.post(
        "/api/v1/auth/change-password",
        headers=initial_h,
        json={"old_password": "Initial@123", "new_password": "Changed@123"},
    )
    check("首次修改密码成功", r.status_code == 200, r.text[:300])
    changed = r.json().get("data") or {}
    check("修改后不再要求改密", changed.get("must_change_password") is False)
    new_h = {"Authorization": f"Bearer {changed['access_token']}"}
    check("首次改密后旧 token 失效", client.get("/api/v1/auth/me", headers=initial_h).status_code == 401)
    check("首次改密后新 token 可进入业务接口", client.get("/api/v1/projects", headers=new_h).status_code == 200)

    print("\n[3] 生命周期字段")
    r = client.patch(
        f"/api/v1/admin/users/{employee_a['id']}",
        headers=admin_h,
        json={"is_active": False, "leave_date": "2026-10-20", "disable_reason": "离职"},
    )
    check("停用员工成功", r.status_code == 200, r.text[:300])
    stopped = r.json().get("data") or {}
    check("离职日期已记录", stopped.get("leave_date") == "2026-10-20")
    check("停用原因已记录", stopped.get("disable_reason") == "离职")
    check("停用时间已记录", bool(stopped.get("disabled_at")))
    check("停用操作人已记录", stopped.get("disabled_by_name") == "系统管理员")
    check("停用后不能再登录", login(client, a_username, "Changed@123").status_code == 403)
    r = client.patch(
        f"/api/v1/admin/users/{employee_a['id']}",
        headers=admin_h,
        json={"is_active": True},
    )
    check("重新启用员工成功", r.status_code == 200, r.text[:300])
    enabled = r.json().get("data") or {}
    check("重新启用后清空停用原因", enabled.get("disable_reason") is None)
    check("重新启用后清空离职日期", enabled.get("leave_date") is None)

    print("\n[4] 批量入职与批量停用")
    bulk_1 = f"bulk1_{suffix}"
    bulk_2 = f"bulk2_{suffix}"
    r = client.post(
        "/api/v1/admin/users/bulk",
        headers=admin_h,
        json={
            "org_id": owner_org["id"],
            "hire_date": "2026-10-15",
            "users": [
                {
                    "username": bulk_1,
                    "password": "Bulk@123",
                    "name": "批量员工一",
                    "employee_no": f"B1{suffix}",
                    "email": f"bulk1_{suffix}@example.com",
                },
                {
                    "username": bulk_2,
                    "password": "Bulk@123",
                    "name": "批量员工二",
                    "employee_no": f"B2{suffix}",
                    "email": f"bulk2_{suffix}@example.com",
                },
            ],
        },
    )
    check("批量入职两名员工成功", r.status_code == 201, r.text[:400])
    bulk_data = r.json().get("data") or {}
    check("批量入职返回数量正确", bulk_data.get("created_count") == 2)
    bulk_users = bulk_data.get("users") or []
    check("批量员工均记录入职日期", all(u.get("hire_date") == "2026-10-15" for u in bulk_users))
    check("批量员工均要求首次改密", all(u.get("must_change_password") for u in bulk_users))

    dup_1 = f"dup1_{suffix}"
    dup_2 = f"dup2_{suffix}"
    r = client.post(
        "/api/v1/admin/users/bulk",
        headers=admin_h,
        json={
            "org_id": owner_org["id"],
            "users": [
                {
                    "username": dup_1,
                    "password": "Bulk@123",
                    "name": "重复一",
                    "employee_no": f"D{suffix}",
                },
                {
                    "username": dup_2,
                    "password": "Bulk@123",
                    "name": "重复二",
                    "employee_no": f"D{suffix}",
                },
            ],
        },
    )
    check("批量内部重复工号整体拒绝", r.status_code == 409, r.text[:300])
    check("批量失败后不会部分创建", not pool(client, admin_h, dup_1))

    r = client.post(
        "/api/v1/admin/users/bulk-disable",
        headers=admin_h,
        json={
            "user_ids": [u["id"] for u in bulk_users],
            "leave_date": "2026-10-21",
            "disable_reason": "批量离职",
        },
    )
    check("批量停用成功", r.status_code == 200, r.text[:300])
    disabled = r.json().get("data") or {}
    check("批量停用返回数量正确", disabled.get("disabled_count") == 2)
    check("批量停用记录离职日期", all(u.get("leave_date") == "2026-10-21" for u in disabled.get("users") or []))
    check("批量停用记录原因", all(u.get("disable_reason") == "批量离职" for u in disabled.get("users") or []))
    check("批量停用后不能登录", login(client, bulk_1, "Bulk@123").status_code == 403)

    print("\n[5] 部门范围与审计")
    unit_h = auth_headers(client, "ouyuxin")
    r = client.post(
        "/api/v1/admin/users/bulk",
        headers=unit_h,
        json={
            "org_id": owner_org["id"],
            "users": [{"username": f"cross_bulk_{suffix}", "password": "Bulk@123", "name": "越权批量"}],
        },
    )
    check("部门管理员不能跨部门批量入职", r.status_code == 403, r.text[:300])
    r = client.post(
        "/api/v1/admin/users/bulk",
        headers=unit_h,
        json={
            "org_id": tjad_org["id"],
            "users": [{"username": f"unit_bulk_{suffix}", "password": "Bulk@123", "name": "本部门批量"}],
        },
    )
    check("部门管理员可在本部门批量入职", r.status_code == 201, r.text[:300])
    r = client.post(
        "/api/v1/admin/users/bulk-disable",
        headers=unit_h,
        json={"user_ids": [employee_a["id"]], "leave_date": "2026-10-22", "disable_reason": "越权"},
    )
    check("部门管理员不能跨部门批量停用", r.status_code == 400, r.text[:300])

    unit_admin_row = next(
        u
        for u in (client.get("/api/v1/admin/users", headers=admin_h, params={"keyword": "ouyuxin"}).json().get("data") or [])
        if u.get("username") == "ouyuxin"
    )
    r = client.post(
        "/api/v1/admin/users/bulk-disable",
        headers=admin_h,
        json={"user_ids": [unit_admin_row["id"]], "leave_date": "2026-10-22", "disable_reason": "批量"},
    )
    check("管理员账号不能被批量停用", r.status_code == 400, r.text[:300])

    db = SessionLocal()
    try:
        actions = set(
            db.execute(
                select(AuditLog.action).where(
                    AuditLog.action.in_(["BULK_CREATE", "BULK_DISABLE"])
                )
            ).scalars().all()
        )
    finally:
        db.close()
    check("批量入职与批量停用均有审计", {"BULK_CREATE", "BULK_DISABLE"}.issubset(actions), str(actions))

    print(f"\n员工管理增强：通过 {passed} 项，失败 {failed} 项")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
