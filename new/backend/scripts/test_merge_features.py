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

    print("\n[2] 工作台新建项目")
    r = client.post(
        "/api/v1/projects",
        headers=h,
        json={
            "name": "合并版自动化测试项目",
            "short_name": "合并测试",
            "city": "杭州市",
            "location": "杭州市测试区",
            "project_type": "商业综合体",
            "scale_desc": "测试桩 10 根",
        },
    )
    check("新建项目返回 201", r.status_code == 201, r.text[:300])
    project = r.json().get("data") or {}
    pid = project.get("id")
    check("返回项目 id", bool(pid))
    check("自动建立 7 个阶段", len(project.get("stages") or []) == 7)
    check("默认从前期调研开始", project.get("current_stage_code") == "PRE_SURVEY")
    check("创建人以设计单位身份加入", project.get("my_unit") == "DESIGNER")

    print("\n[3] 编辑项目与权限过滤")
    r = client.patch(
        f"/api/v1/projects/{pid}",
        headers=h,
        json={"short_name": "合并测试改", "scale_desc": "测试桩 20 根"},
    )
    check("编辑项目返回 200", r.status_code == 200, r.text[:300])
    updated = r.json().get("data") or {}
    check("简称已更新", updated.get("short_name") == "合并测试改")
    check("规模已更新", updated.get("scale_desc") == "测试桩 20 根")

    r = client.get("/api/v1/projects", headers=h)
    visible = r.json().get("data") or []
    check("新项目出现在创建人工作台", any(x.get("id") == pid for x in visible))

    r = client.get("/api/v1/catalog/documents")
    check("未登录不能读取标准清单", r.status_code == 401, str(r.status_code))

    print(f"\n合并版新增能力：通过 {passed} 项，失败 {failed} 项")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
