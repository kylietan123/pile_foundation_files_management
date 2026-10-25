"""部门管理员权限管理测试。

覆盖：部门管理员进入权限管理页、仅管理本部门账号、创建账号并分配本项目权限、
不能重置密码、不能越权到其他部门、停用账号即吊销全部项目权限、可重新启用。
"""
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


def login(client: TestClient, username: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def headers(client: TestClient, username: str, password: str = PASSWORD) -> dict[str, str]:
    r = login(client, username, password)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def main() -> int:
    client = TestClient(app)
    suffix = str(int(time.time()))
    employee_username = f"unit_emp_{suffix}"
    peer_username = f"unit_peer_{suffix}"

    print("\n[1] 部门管理员身份与页面范围")
    unit_h = headers(client, "ouyuxin")
    r = client.get("/api/v1/auth/me", headers=unit_h)
    me = r.json().get("data") or {}
    check("部门管理员可读取个人信息", r.status_code == 200, r.text[:200])
    check(
        "个人信息带部门管理员标记",
        any(o.get("is_unit_admin") for o in me.get("orgs") or []),
        str(me.get("orgs")),
    )

    r = client.get("/api/v1/admin/overview", headers=unit_h)
    overview = r.json().get("data") or {}
    check("部门管理员可进入权限管理页", r.status_code == 200, r.text[:300])
    check("概览标记为部门范围", overview.get("scope") == "UNIT", str(overview))
    check(
        "概览仅包含本部门",
        "同济大学建筑设计研究院" in (overview.get("managed_org_names") or []),
        str(overview.get("managed_org_names")),
    )

    r = client.get("/api/v1/admin/options", headers=unit_h)
    options = r.json().get("data") or {}
    check("部门管理员可读取权限选项", r.status_code == 200, r.text[:300])
    orgs = options.get("orgs") or []
    units = options.get("units") or []
    check("只能看到本部门单位", len(orgs) == 1 and orgs[0].get("name") == "同济大学建筑设计研究院", str(orgs))
    check("只能看到本单位参与类型", len(units) == 1 and units[0].get("code") == "DESIGNER", str(units))
    designer_stages = (options.get("unit_stages") or {}).get("DESIGNER") or []
    check("阶段选项按本部门责任过滤", "DESIGN" in designer_stages and "PRE_SURVEY" not in designer_stages, str(designer_stages))
    check("能看到本部门参与的项目", len(options.get("projects") or []) > 0, str(options.get("projects")))

    r = client.get("/api/v1/admin/users", headers=unit_h)
    listed = r.json().get("data") or []
    check("部门管理员可读取本部门账号", r.status_code == 200, r.text[:300])
    check("账号列表不包含总管理员", all(u.get("username") != "admin" for u in listed), str([u.get("username") for u in listed]))
    check("账号列表包含本部门员工", all(any(o.get("name") == "同济大学建筑设计研究院" for o in u.get("orgs") or []) for u in listed))

    regular_h = headers(client, "haoxirui")
    r = client.get("/api/v1/admin/users", headers=regular_h)
    check("普通员工仍不能进入权限管理页", r.status_code == 403, str(r.status_code))

    print("\n[2] 部门管理员的边界")
    admin_h = headers(client, "admin")
    all_options = (client.get("/api/v1/admin/options", headers=admin_h).json().get("data") or {})
    other_org = next(o for o in all_options.get("orgs") or [] if o.get("name") != "同济大学建筑设计研究院")

    r = client.post(
        "/api/v1/admin/users",
        headers=unit_h,
        json={
            "username": f"cross_{suffix}",
            "password": "NewUser@123",
            "name": "越权测试员工",
            "org_id": other_org["id"],
        },
    )
    check("不能在其他部门创建账号", r.status_code == 403, r.text[:300])

    r = client.post(
        "/api/v1/admin/users",
        headers=unit_h,
        json={
            "username": f"adminflag_{suffix}",
            "password": "NewUser@123",
            "name": "越权管理员",
            "org_id": orgs[0]["id"],
            "is_unit_admin": True,
        },
    )
    check("不能自行创建部门管理员", r.status_code == 403, r.text[:300])

    r = client.post(
        "/api/v1/admin/users",
        headers=unit_h,
        json={
            "username": f"superflag_{suffix}",
            "password": "NewUser@123",
            "name": "越权总管理员",
            "org_id": orgs[0]["id"],
            "is_superuser": True,
        },
    )
    check("不能自行创建总管理员", r.status_code == 403, r.text[:300])

    r = client.post(
        "/api/v1/admin/users/admin/reset-password",
        headers=unit_h,
        json={"password": "Reset@123"},
    )
    check("部门管理员不能重置密码", r.status_code == 403, r.text[:300])

    print("\n[3] 创建本部门员工并分配项目权限")
    project = (options.get("projects") or [])[0]
    r = client.post(
        "/api/v1/admin/users",
        headers=unit_h,
        json={
            "username": employee_username,
            "password": "NewUser@123",
            "name": "部门新员工",
            "employee_no": f"UNIT-{suffix}",
            "title": "助理工程师",
            "org_id": orgs[0]["id"],
            "assignments": [
                {
                    "project_id": project["id"],
                    "unit_code": "DESIGNER",
                    "stage_scope": ["DESIGN"],
                }
            ],
        },
    )
    check("创建本部门员工成功", r.status_code == 201, r.text[:400])
    created = r.json().get("data") or {}
    check("员工归属本部门", (created.get("orgs") or [{}])[0].get("name") == "同济大学建筑设计研究院")
    check("已分配一个项目权限", len(created.get("memberships") or []) == 1, str(created.get("memberships")))

    emp_h = headers(client, employee_username, "NewUser@123")
    employee_me = client.get("/api/v1/auth/me", headers=emp_h).json().get("data") or {}
    membership = next(
        (m for m in employee_me.get("memberships") or [] if m.get("project_id") == project["id"]),
        None,
    )
    check("新员工登录后能看到被分配的项目", membership is not None, str(employee_me.get("memberships")))
    check("设计阶段获得主办权限", membership is not None and "EDIT" in (membership.get("actions") or []), str(membership))

    r = client.post(
        f"/api/v1/admin/users/{created['id']}/permissions",
        headers=unit_h,
        json={
            "project_id": project["id"],
            "unit_code": "DESIGNER",
            "stage_scope": ["PRE_SURVEY"],
        },
    )
    check("不能分配本部门无责任的阶段", r.status_code == 403, r.text[:300])

    r = client.patch(
        f"/api/v1/admin/users/{created['id']}",
        headers=unit_h,
        json={"name": "部门员工改名", "title": "工程师"},
    )
    check("部门管理员可维护本部门员工资料", r.status_code == 200, r.text[:300])
    check("员工资料修改生效", (r.json().get("data") or {}).get("name") == "部门员工改名")

    r = client.patch(
        f"/api/v1/admin/users/{created['id']}",
        headers=unit_h,
        json={"is_unit_admin": True},
    )
    check("不能把员工提升为部门管理员", r.status_code == 403, r.text[:300])

    print("\n[4] 取消项目权限与离职停用")
    member_id = (created.get("memberships") or [{}])[0].get("id")
    r = client.delete(
        f"/api/v1/admin/users/{created['id']}/permissions/{member_id}",
        headers=unit_h,
    )
    check("可取消单个项目权限", r.status_code == 200, r.text[:300])
    check("取消后项目权限为空", len((r.json().get("data") or {}).get("memberships") or []) == 0)
    employee_me = client.get("/api/v1/auth/me", headers=emp_h).json().get("data") or {}
    check(
        "员工立即失去该项目访问权",
        all(m.get("project_id") != project["id"] for m in employee_me.get("memberships") or []),
        str(employee_me.get("memberships")),
    )

    r = client.post(
        f"/api/v1/admin/users/{created['id']}/permissions",
        headers=unit_h,
        json={
            "project_id": project["id"],
            "unit_code": "DESIGNER",
            "stage_scope": ["DESIGN"],
        },
    )
    check("可重新分配项目权限", r.status_code == 200, r.text[:300])

    r = client.patch(
        f"/api/v1/admin/users/{created['id']}",
        headers=unit_h,
        json={"is_active": False},
    )
    check("部门管理员可停用离职员工", r.status_code == 200, r.text[:300])
    stopped = r.json().get("data") or {}
    check("停用即吊销全部项目权限", len(stopped.get("memberships") or []) == 0, str(stopped.get("memberships")))
    check("停用后账号仍保留在列表中", any(u.get("id") == created["id"] for u in (client.get("/api/v1/admin/users", headers=unit_h).json().get("data") or [])))
    check("停用后不能登录", login(client, employee_username, "NewUser@123").status_code == 403)
    check("停用后旧 access token 立即失效", client.get("/api/v1/auth/me", headers=emp_h).status_code == 401)

    r = client.post(
        f"/api/v1/admin/users/{created['id']}/permissions",
        headers=unit_h,
        json={
            "project_id": project["id"],
            "unit_code": "DESIGNER",
            "stage_scope": ["DESIGN"],
        },
    )
    check("停用账号不能重新分配项目权限", r.status_code == 400, r.text[:300])
    r = client.post(
        f"/api/v1/admin/users/{created['id']}/permissions",
        headers=admin_h,
        json={
            "project_id": project["id"],
            "unit_code": "DESIGNER",
            "stage_scope": ["DESIGN"],
        },
    )
    check("总管理员也不能给停用账号分配权限", r.status_code == 400, r.text[:300])

    r = client.patch(
        f"/api/v1/admin/users/{created['id']}",
        headers=unit_h,
        json={"is_active": True},
    )
    check("可重新启用离职员工账号", r.status_code == 200, r.text[:300])
    check("重新启用后账号可登录", login(client, employee_username, "NewUser@123").status_code == 200)
    check(
        "重新启用不会自动恢复旧权限",
        len((r.json().get("data") or {}).get("memberships") or []) == 0,
        str((r.json().get("data") or {}).get("memberships")),
    )
    check("重新启用后停用前的旧 token 仍失效", client.get("/api/v1/auth/me", headers=emp_h).status_code == 401)

    r = login(client, employee_username, "NewUser@123")
    reactivated_h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    check("重新启用后可重新获取新会话", client.get("/api/v1/auth/me", headers=reactivated_h).status_code == 200)

    r = client.post(
        f"/api/v1/admin/users/{created['id']}/reset-password",
        headers=admin_h,
        json={"password": "Reset@123"},
    )
    check("总管理员可重置员工密码", r.status_code == 200, r.text[:300])
    check("重置密码后旧 access token 立即失效", client.get("/api/v1/auth/me", headers=reactivated_h).status_code == 401)
    check("重置后旧密码不能登录", login(client, employee_username, "NewUser@123").status_code == 401)
    r = login(client, employee_username, "Reset@123")
    check("重置后新密码可以登录", r.status_code == 200, r.text[:200])
    check("重置密码后再次要求首次改密", (r.json().get("data") or {}).get("must_change_password") is True)
    reset_h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    check("重置密码后未改密不能进入业务接口", client.get("/api/v1/projects", headers=reset_h).status_code == 403)

    print("\n[5] 审计日志")
    db = SessionLocal()
    try:
        account_actions = set(
            db.execute(
                select(AuditLog.action).where(AuditLog.target_id == created["id"])
            ).scalars().all()
        )
        membership_actions = set(
            db.execute(
                select(AuditLog.action).where(
                    AuditLog.target_type == "project_member",
                    AuditLog.target_name.like("%部门员工改名%"),
                )
            ).scalars().all()
        )
        failed_logins = db.execute(
            select(AuditLog).where(
                AuditLog.action == "LOGIN",
                AuditLog.success.is_(False),
                AuditLog.target_name == employee_username,
            )
        ).scalars().all()
        success_logins = db.execute(
            select(AuditLog).where(
                AuditLog.action == "LOGIN",
                AuditLog.success.is_(True),
                AuditLog.target_id == created["id"],
            )
        ).scalars().all()
    finally:
        db.close()

    check(
        "账号创建/修改/停用/启用/重置密码都有审计",
        {"CREATE", "UPDATE", "DISABLE", "ENABLE", "RESET_PASSWORD"}.issubset(account_actions),
        str(account_actions),
    )
    check(
        "项目授权/取消权限都有审计",
        {"GRANT", "REVOKE"}.issubset(membership_actions),
        str(membership_actions),
    )
    check("登录失败有审计", len(failed_logins) > 0, str(failed_logins))
    check("登录成功有审计", len(success_logins) > 0, str(success_logins))

    print("\n[6] 不能管理其他管理员")
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_h,
        json={
            "username": peer_username,
            "password": "NewUser@123",
            "name": "同部门管理员",
            "org_id": orgs[0]["id"],
            "is_unit_admin": True,
        },
    )
    check("总管理员可创建同部门管理员", r.status_code == 201, r.text[:300])
    peer_id = (r.json().get("data") or {}).get("id")

    r = client.patch(
        f"/api/v1/admin/users/{peer_id}",
        headers=unit_h,
        json={"is_active": False},
    )
    check("部门管理员不能停用其他管理员", r.status_code == 403, r.text[:300])

    owner_row = next(
        u
        for u in (client.get(
            "/api/v1/admin/users", headers=admin_h, params={"keyword": "chenkaili"}
        ).json().get("data") or [])
        if u.get("username") == "chenkaili"
    )
    r = client.patch(
        f"/api/v1/admin/users/{owner_row['id']}",
        headers=unit_h,
        json={"is_active": False},
    )
    check("不能管理其他部门账号", r.status_code == 403, r.text[:300])

    print(f"\n部门管理员权限：通过 {passed} 项，失败 {failed} 项")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
