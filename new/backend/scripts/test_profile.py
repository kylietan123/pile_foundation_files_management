"""个人设置测试：个人资料修改、原密码校验与登录密码修改。"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSWORD = "Tjad@2026"
NEW_PASSWORD = "Profile@123"
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


def main() -> int:
    client = TestClient(app)

    print("\n[1] 修改个人资料")
    r = client.post("/api/v1/auth/login", json={"username": "ouyuxin", "password": PASSWORD})
    check("用户登录成功", r.status_code == 200, r.text[:200])
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = client.patch(
        "/api/v1/auth/me",
        headers=h,
        json={"phone": "13800000000", "email": "profile-test@example.com"},
    )
    check("修改资料返回 200", r.status_code == 200, r.text[:300])
    me = r.json().get("data") or {}
    check("手机修改成功", me.get("phone") == "13800000000")
    check("邮箱修改成功", me.get("email") == "profile-test@example.com")
    r = client.patch(
        "/api/v1/auth/me",
        headers=h,
        json={"name": "员工自行改名", "title": "员工自行改职称"},
    )
    check("员工不能自行修改姓名和职称", r.status_code == 422, str(r.status_code))

    print("\n[2] 修改登录密码")
    r = client.post(
        "/api/v1/auth/change-password",
        headers=h,
        json={"old_password": "wrong-password", "new_password": NEW_PASSWORD},
    )
    check("原密码错误时拒绝修改", r.status_code == 400, str(r.status_code))

    r = client.post(
        "/api/v1/auth/change-password",
        headers=h,
        json={"old_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    check("原密码正确时修改成功", r.status_code == 200, r.text[:200])
    changed = r.json().get("data") or {}
    check("修改密码后返回新 access token", bool(changed.get("access_token")), str(changed)[:200])
    new_h = {"Authorization": f"Bearer {changed.get('access_token')}"}
    check("修改密码后旧 access token 立即失效", client.get("/api/v1/auth/me", headers=h).status_code == 401)
    check("修改密码后新 access token 可继续使用", client.get("/api/v1/auth/me", headers=new_h).status_code == 200)

    r = client.post("/api/v1/auth/login", json={"username": "ouyuxin", "password": PASSWORD})
    check("旧密码不能继续登录", r.status_code == 401, str(r.status_code))
    r = client.post("/api/v1/auth/login", json={"username": "ouyuxin", "password": NEW_PASSWORD})
    check("新密码可以登录", r.status_code == 200, r.text[:200])

    print(f"\n个人设置：通过 {passed} 项，失败 {failed} 项")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
