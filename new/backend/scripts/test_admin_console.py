"""系统管理控制台测试。

覆盖管理员创建账号、分配项目/阶段权限、重置密码和启停账号。
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

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


def main() -> int:
    client = TestClient(app)

    print("\n[1] 管理员登录与控制台权限")
    r = login(client, "admin")
    check("管理员登录成功", r.status_code == 200, r.text[:200])
    admin_h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = client.get("/api/v1/admin/overview", headers=admin_h)
    check("管理员可读取管理概览", r.status_code == 200, r.text[:200])
    overview = r.json().get("data") or {}
    check("概览包含账号总数", overview.get("user_count", 0) >= 12, str(overview))

    r = login(client, "haoxirui")
    employee_h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    r = client.get("/api/v1/admin/overview", headers=employee_h)
    check("普通员工不能访问管理控制台", r.status_code == 403, str(r.status_code))

    print("\n[2] 管理选项")
    r = client.get("/api/v1/admin/options", headers=admin_h)
    check("读取单位/项目/阶段选项", r.status_code == 200, r.text[:200])
    options = r.json().get("data") or {}
    check("包含参与单位", len(options.get("orgs") or []) > 0)
    check("包含项目", len(options.get("projects") or []) > 0)
    check("包含七个阶段", len(options.get("stages") or []) == 7)

    org = options["orgs"][0]
    project = options["projects"][0]
    username = "admin_created_user"

    print("\n[3] 创建员工账号并分配权限")
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_h,
        json={
            "username": username,
            "password": "NewUser@123",
            "name": "控制台测试员工",
            "employee_no": "TEST-001",
            "title": "测试工程师",
            "org_id": org["id"],
            "is_unit_admin": True,
            "assignments": [
                {
                    "project_id": project["id"],
                    "stage_scope": ["CONSTRUCTION"],
                    "responsibility": "PRIMARY",
                }
            ],
        },
    )
    check("创建账号返回 201", r.status_code == 201, r.text[:300])
    created = r.json().get("data") or {}
    check("账号名称正确", created.get("name") == "控制台测试员工")
    check("已分配 1 个项目权限", len(created.get("memberships") or []) == 1)
    check("可设置为单位管理员", (created.get("orgs") or [{}])[0].get("is_unit_admin") is True)

    r = client.get("/api/v1/admin/users", headers=admin_h, params={"keyword": username})
    check("账号可被管理员检索", len(r.json().get("data") or []) == 1)

    r = client.patch(
        f"/api/v1/admin/users/{created['id']}",
        headers=admin_h,
        json={"name": "管理员修改姓名", "title": "高级工程师"},
    )
    check("管理员可修改姓名和职称", r.status_code == 200, r.text[:300])
    edited = r.json().get("data") or {}
    check("管理员修改姓名生效", edited.get("name") == "管理员修改姓名")
    check("管理员修改职称生效", edited.get("title") == "高级工程师")

    r = login(client, username, "NewUser@123")
    check("新员工可以登录", r.status_code == 200, r.text[:200])
    new_h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=new_h).json()["data"]
    membership = next(x for x in me["memberships"] if x["project_id"] == project["id"])
    check("施工阶段被授予编辑权限", "EDIT" in membership["actions"], str(membership["actions"]))

    print("\n[4] 重置密码与启停账号")
    r = client.post(
        f"/api/v1/admin/users/{created['id']}/reset-password",
        headers=admin_h,
        json={"password": "Reset@123"},
    )
    check("管理员可重置密码", r.status_code == 200, r.text[:200])
    check("新密码可登录", login(client, username, "Reset@123").status_code == 200)

    r = client.patch(
        f"/api/v1/admin/users/{created['id']}",
        headers=admin_h,
        json={"is_active": False},
    )
    check("管理员可禁用账号", r.status_code == 200, r.text[:200])
    check("禁用后不能登录", login(client, username, "Reset@123").status_code == 403)

    print(f"\n管理控制台：通过 {passed} 项，失败 {failed} 项")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
