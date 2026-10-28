"""合并版新增能力测试。

覆盖：
  1. kylie 版 84 类标准文档清单接口
  2. hxr 版工作台新建/编辑项目接口
  3. 新建项目自动建立 7 阶段与创建人成员关系
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


def main() -> int:
    client = TestClient(app)

    print("\n[1] 合并版标准文档清单")
    r = client.post("/api/v1/auth/login", json={"username": "ouyuxin", "password": PASSWORD})
    check("登录成功", r.status_code == 200, r.text[:200])
    token = r.json()["data"]["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/catalog/documents", headers=h)
    check("清单接口返回 200", r.status_code == 200, r.text[:200])
    rows = r.json().get("data") or []
    check("共 84 类文档", len(rows) == 84, str(len(rows)))
    check("施工阶段 32 类", sum(1 for x in rows if x.get("stage_code") == "CONSTRUCTION") == 32)

    r = client.get("/api/v1/catalog/documents?stage=CONSTRUCTION", headers=h)
    check("按阶段过滤生效", len(r.json().get("data") or []) == 32)

    print("\n[2] 项目创建权限与建设单位审核")
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    admin_h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    options = client.get("/api/v1/admin/options", headers=admin_h).json()["data"]
    owner_org = next(o for o in options["orgs"] if o["org_type"] == "OWNER")
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_h,
        json={
            "username": "owner_staff_test",
            "password": "Staff@123",
            "name": "建设单位普通员工",
            "org_id": owner_org["id"],
            "is_unit_admin": False,
        },
    )
    check("管理员创建建设单位普通员工", r.status_code == 201, r.text[:300])
    gc_org = next(o for o in options["orgs"] if o["org_type"] == "GENERAL_CONTRACTOR")
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_h,
        json={
            "username": "gc_staff_test",
            "password": "Staff@123",
            "name": "总包普通员工",
            "org_id": gc_org["id"],
            "is_unit_admin": False,
        },
    )
    check("管理员创建总包普通员工", r.status_code == 201, r.text[:300])
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "owner_staff_test", "password": "Staff@123"},
    )
    staff_h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    r = client.post(
        "/api/v1/projects",
        headers=staff_h,
        json={"name": "普通建设单位员工创建的项目"},
    )
    check("普通建设单位员工可以创建项目", r.status_code == 201, r.text[:300])
    staff_project_id = (r.json().get("data") or {}).get("id")

    r = client.post("/api/v1/auth/login", json={"username": "chenkaili", "password": PASSWORD})
    owner_admin_h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    admin_projects = client.get("/api/v1/projects", headers=owner_admin_h).json().get("data") or []
    check(
        "建设单位管理员能看到普通员工创建的项目",
        any(p.get("id") == staff_project_id for p in admin_projects),
    )

    r = client.post("/api/v1/projects", headers=h, json={"name": "非建设单位不应创建"})
    check("非建设单位不能新建项目", r.status_code == 403, str(r.status_code))

    r = client.post("/api/v1/auth/login", json={"username": "chenkaili", "password": PASSWORD})
    check("建设单位登录成功", r.status_code == 200, r.text[:200])
    owner_h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    r = client.post(
        "/api/v1/projects",
        headers=owner_h,
        json={
            "name": "合并版自动化测试项目",
            "short_name": "合并测试",
            "city": "杭州市",
            "location": "杭州市测试区",
            "project_type": "商业综合体",
            "scale_desc": "测试桩 10 根",
        },
    )
    check("建设单位新建项目返回 201", r.status_code == 201, r.text[:300])
    project = r.json().get("data") or {}
    pid = project.get("id")
    check("返回项目 id", bool(pid))
    check("自动建立 7 个阶段", len(project.get("stages") or []) == 7)
    check("新项目待建设单位管理员审核", project.get("status") == "PREPARING")
    check("创建人以建设单位身份加入", project.get("my_unit") == "OWNER")

    other = client.post(
        f"/api/v1/projects/{pid}/members",
        headers=owner_h,
        json={"user_id": "not-used"},
    )
    check("审核前不能添加其他参与单位", other.status_code == 400, str(other.status_code))

    r = client.post(f"/api/v1/projects/{pid}/approve", headers=owner_h)
    check("建设单位管理员审核通过", r.status_code == 200, r.text[:300])
    approved_project = r.json().get("data") or {}
    check("审核后项目进入进行中", approved_project.get("status") == "IN_PROGRESS")
    stage_owner_ids = {
        s.get("owner_user_id") for s in approved_project.get("stages", []) if s.get("owner_user_id")
    }
    check("七个阶段已设置负责人", len(stage_owner_ids) > 0)
    member_rows = client.get(f"/api/v1/projects/{pid}/members", headers=owner_h).json().get("data") or []
    member_user_ids = {m.get("user_id") for m in member_rows}
    check("阶段负责人已自动加入项目", stage_owner_ids.issubset(member_user_ids))

    r = client.post("/api/v1/auth/login", json={"username": "sunqi", "password": PASSWORD})
    gc_h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    gc_candidates = client.get(
        f"/api/v1/projects/{pid}/member-candidates", headers=gc_h
    ).json().get("data") or []
    gc_staff = next((x for x in gc_candidates if x.get("username") == "gc_staff_test"), None)
    check("施工阶段负责人可看到本单位员工", gc_staff is not None)
    r = client.post(
        f"/api/v1/projects/{pid}/members",
        headers=gc_h,
        json={
            "user_id": gc_staff["user_id"],
            "unit_code": gc_staff["unit_code"],
            "stage_scope": ["DESIGN"],
            "responsibility": "PARTICIPANT",
        },
    )
    check("阶段负责人不能分配其他阶段", r.status_code == 403, str(r.status_code))
    r = client.post(
        f"/api/v1/projects/{pid}/members",
        headers=gc_h,
        json={
            "user_id": gc_staff["user_id"],
            "unit_code": gc_staff["unit_code"],
            "stage_scope": ["CONSTRUCTION"],
            "responsibility": "PARTICIPANT",
        },
    )
    check("阶段负责人可给本单位分配本阶段权限", r.status_code == 200, r.text[:300])

    r = client.get(f"/api/v1/projects/{pid}/member-candidates", headers=owner_h)
    check("审核后可获取参与人员候选", r.status_code == 200, r.text[:200])
    candidates = r.json().get("data") or []
    check("存在可添加员工", len(candidates) > 0)
    candidate = candidates[0]
    r = client.post(
        f"/api/v1/projects/{pid}/members",
        headers=owner_h,
        json={
            "user_id": candidate["user_id"],
            "unit_code": candidate["unit_code"],
            "stage_scope": ["CONSTRUCTION"],
            "responsibility": "PRIMARY",
        },
    )
    check("审核后可添加其他参与单位", r.status_code == 200, r.text[:300])

    print("\n[3] 编辑项目与权限过滤")
    r = client.patch(
        f"/api/v1/projects/{pid}",
        headers=owner_h,
        json={"short_name": "合并测试改", "scale_desc": "测试桩 20 根"},
    )
    check("编辑项目返回 200", r.status_code == 200, r.text[:300])
    updated = r.json().get("data") or {}
    check("简称已更新", updated.get("short_name") == "合并测试改")
    check("规模已更新", updated.get("scale_desc") == "测试桩 20 根")

    r = client.get("/api/v1/projects", headers=owner_h)
    visible = r.json().get("data") or []
    check("新项目出现在建设单位工作台", any(x.get("id") == pid for x in visible))

    r = client.get("/api/v1/catalog/documents")
    check("未登录不能读取标准清单", r.status_code == 401, str(r.status_code))

    print("\n[4] 建设单位施工阶段上传覆盖")
    r = client.post(
        "/api/v1/projects",
        headers=owner_h,
        json={
            "name": "建设单位施工上传自动化测试项目",
            "start_stage": "CONSTRUCTION",
            "owner_primary_construction": True,
        },
    )
    check("建设单位创建施工演示项目", r.status_code == 201, r.text[:300])
    owner_project = r.json().get("data") or {}
    check("施工演示项目先进入待审核", owner_project.get("status") == "PREPARING")
    r = client.post(f"/api/v1/projects/{owner_project['id']}/approve", headers=owner_h)
    check("施工演示项目审核通过", r.status_code == 200, r.text[:200])
    me_owner = client.get("/api/v1/auth/me", headers=owner_h).json().get("data") or {}
    owner_membership = next(
        (m for m in me_owner.get("memberships", []) if m.get("project_id") == owner_project.get("id")),
        {},
    )
    check("身份为建设施工单位", owner_membership.get("unit_code") == "OWNER")
    check("施工阶段是主办阶段", "CONSTRUCTION" in (owner_membership.get("primary_stages") or []))
    check("施工阶段有上传编辑权限", "EDIT" in (owner_membership.get("actions") or []))

    print(f"\n合并版新增能力：通过 {passed} 项，失败 {failed} 项")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
