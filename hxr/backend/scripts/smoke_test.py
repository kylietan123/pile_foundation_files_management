"""后端冒烟测试。

验证的核心不是"接口能返回数据"，而是**权限是否真的生效**：
  1. 登录能拿到 token
  2. /auth/me 返回的角色与阶段范围**随项目变化**
  3. 项目列表**自动按权限过滤**
  4. 无权限的项目返回 403 且区分"无角色"与"无数据范围"
  5. 未认证请求被拒绝

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/smoke_test.py
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

    # ---------- 1. 健康检查 ----------
    print("\n[1] 健康检查")
    r = client.get("/api/v1/health")
    check("GET /health 返回 200", r.status_code == 200, f"got {r.status_code}")
    body = r.json()
    check("统一包体包含 code/message/data", all(k in body for k in ("code", "message", "data")))
    check("code == 0", body.get("code") == 0, str(body.get("code")))

    # ---------- 2. 未认证被拒 ----------
    print("\n[2] 未认证访问被拒绝")
    r = client.get("/api/v1/projects")
    check("无 token 访问 /projects 返回 401", r.status_code == 401, f"got {r.status_code}")
    r = client.get("/api/v1/auth/me")
    check("无 token 访问 /auth/me 返回 401", r.status_code == 401, f"got {r.status_code}")

    # ---------- 3. 错误密码 ----------
    print("\n[3] 认证校验")
    r = client.post("/api/v1/auth/login", json={"username": "ouyuxin", "password": "wrong"})
    check("错误密码返回 401", r.status_code == 401, f"got {r.status_code}")
    r = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    check("不存在用户返回 401（不泄露账号是否存在）", r.status_code == 401, f"got {r.status_code}")

    # ---------- 4. 登录成功 ----------
    print("\n[4] 欧雨欣登录")
    r = client.post("/api/v1/auth/login", json={"username": "ouyuxin", "password": PASSWORD})
    check("登录返回 200", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    token = r.json()["data"]["access_token"]
    check("返回 access_token", bool(token))
    h = {"Authorization": f"Bearer {token}"}

    # ---------- 5. /auth/me 角色随项目变化（核心卖点）----------
    print("\n[5] 同一人在不同项目角色不同（权限一份配置全局生效）")
    r = client.get("/api/v1/auth/me", headers=h)
    check("/auth/me 返回 200", r.status_code == 200, f"got {r.status_code}")
    me = r.json()["data"]
    check("返回 4 个项目的成员关系", len(me["memberships"]) == 4, f"got {len(me['memberships'])}")

    by_project = {m["project_name"]: m for m in me["memberships"]}

    hz = next((m for n, m in by_project.items() if n and "杭州" in n), None)
    sz = next((m for n, m in by_project.items() if n and "苏州" in n), None)
    check("杭州项目存在", hz is not None)
    check("苏州项目存在", sz is not None)

    if hz:
        # 新模型：主体是「参与单位 × 阶段 × 责任等级」，不再是岗位角色。
        # 欧雨欣在杭州项目是**设计单位**，矩阵里设计阶段是主要责任。
        check("杭州项目参与单位 = DESIGNER（设计单位）",
              hz["unit_code"] == "DESIGNER", hz["unit_code"])
        check("杭州项目责任等级 = PRIMARY（主要责任）",
              hz["responsibility"] == "PRIMARY", str(hz.get("responsibility")))
        # 阶段范围由矩阵推导：设计单位参与 5 个阶段，其中主办 1 个
        # 设计单位可见 6 个阶段：设计试桩/设计/施工/验收试桩/运维监测，
        # 外加**勘察**（设计必须参照勘察资料，定为参与/只读）
        check("设计单位可见 6 个阶段",
              len(hz["stages"]) == 6, str(hz["stages"]))
        check("设计单位主办阶段 = 设计",
              hz["primary_stages"] == ["DESIGN"], str(hz["primary_stages"]))
        check("设计单位在设计阶段有 EDIT 权限", "EDIT" in hz["actions"], str(hz["actions"]))
    if sz:
        # 苏州项目欧雨欣是**勘察单位** —— 同一人在不同项目身份不同
        check("苏州项目参与单位 = SURVEYOR（勘察单位）",
              sz["unit_code"] == "SURVEYOR", sz["unit_code"])
        check("勘察单位身份与杭州不同",
              sz["unit_code"] != (hz["unit_code"] if hz else None),
              f"{sz['unit_code']} vs {hz['unit_code'] if hz else None}")
        check("勘察单位有 EDIT 权限（勘察阶段是主办）",
              "EDIT" in sz["actions"], str(sz["actions"]))

    # ---------- 6. 项目列表按权限过滤 ----------
    print("\n[6] 项目列表按权限过滤")
    r = client.get("/api/v1/projects", headers=h)
    check("GET /projects 返回 200", r.status_code == 200, f"got {r.status_code}")
    projects = r.json()["data"]
    check("欧雨欣可见 4 个项目", len(projects) == 4, f"got {len(projects)}")

    hz_p = next((p for p in projects if "杭州" in p["name"]), None)
    check("杭州项目在列表中", hz_p is not None)
    if hz_p:
        check("杭州项目带 my_unit", hz_p["my_unit"] == "DESIGNER", str(hz_p["my_unit"]))
        check("杭州项目带 my_primary_stages = [DESIGN]",
              hz_p["my_primary_stages"] == ["DESIGN"], str(hz_p["my_primary_stages"]))
        # 展示用责任等级必须与参与单位表一致。
        # 曾经这里是空的（把 None 当阶段码传进 responsibility_in_stage，
        # 永远匹配不到），导致项目卡片上"责任等级"缺失，
        # 而同一个单位在参与单位表里却显示"主要责任"—— 两处自相矛盾。
        check("杭州项目带 my_responsibility = PRIMARY",
              hz_p["my_responsibility"] == "PRIMARY", str(hz_p["my_responsibility"]))
        check("杭州项目带 my_responsibility_label",
              hz_p["my_responsibility_label"] == "主要责任",
              str(hz_p["my_responsibility_label"]))
        check("杭州项目带 my_stages（非空）",
              bool(hz_p["my_stages"]), str(hz_p["my_stages"]))
        check("杭州项目带 7 个阶段", len(hz_p["stages"]) == 7, f"got {len(hz_p['stages'])}")
        check("当前阶段 = DESIGN", hz_p["current_stage_code"] == "DESIGN", hz_p["current_stage_code"])
        design_stage = next((s for s in hz_p["stages"] if s["stage_code"] == "DESIGN"), None)
        check("设计阶段进度 = 68", design_stage and design_stage["progress"] == 68,
              str(design_stage["progress"] if design_stage else None))
        check("设计阶段状态 = IN_PROGRESS",
              design_stage and design_stage["status"] == "IN_PROGRESS",
              str(design_stage["status"] if design_stage else None))

    # ---------- 7. 项目详情权限断言 ----------
    print("\n[7] 项目详情与权限断言")
    if hz_p:
        r = client.get(f"/api/v1/projects/{hz_p['id']}", headers=h)
        check("有权限的项目详情返回 200", r.status_code == 200, f"got {r.status_code}")

        r = client.get(f"/api/v1/projects/{hz_p['id']}/members", headers=h)
        check("项目参与人接口返回 200", r.status_code == 200, f"got {r.status_code}")
        if r.status_code == 200:
            members = r.json()["data"]
            # 杭州项目刻意配齐七个阶段的主办单位：建设单位、勘察单位、
            # 设计试桩单位、设计单位、总包单位、验收试桩单位、检测监测单位，
            # 另有分包、监理、政府审查单位。
            # 共 12 条参与关系（郝兮睿身兼勘察与设计试桩两个单位）。
            check("杭州项目有 12 条参与关系", len(members) == 12, f"got {len(members)}")

    r = client.get("/api/v1/projects/does-not-exist", headers=h)
    check("不存在的项目返回 403（无角色）或 404",
          r.status_code in (403, 404), f"got {r.status_code}")

    # ---------- 8. 不同角色看到不同项目数 ----------
    print("\n[8] 不同用户可见项目数不同")
    # 可见项目数取决于"他是哪些项目的参与单位成员"：
    #   李工（勘察单位）—— 只参与杭州
    #   王五（监理单位）—— 杭州 + 苏州
    #   孙七（总包单位）—— 杭州 + 上海
    for username, expected in [("ligong", 1), ("wangwu", 2), ("sunqi", 2)]:
        r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
        if r.status_code != 200:
            check(f"{username} 登录成功", False, f"got {r.status_code}")
            continue
        h2 = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
        r = client.get("/api/v1/projects", headers=h2)
        n = len(r.json()["data"])
        check(f"{username} 可见 {expected} 个项目", n == expected, f"got {n}")

    # ---------- 9. 字典 ----------
    print("\n[9] 字典（统一 ID 原则的对外入口）")
    r = client.get("/api/v1/dict/categories", headers=h)
    check("字典分类接口返回 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        cats = r.json()["data"]
        check("返回 11 个字典分类", len(cats) == 11, f"got {len(cats)}")

    r = client.get("/api/v1/dict/items", params={"category": "PILE_TYPE"}, headers=h)
    check("按分类取桩型返回 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        piles = r.json()["data"]
        check("返回 6 种桩型", len(piles) == 6, f"got {len(piles)}")
        names = [p["name"] for p in piles]
        check("包含 钻孔灌注桩 φ1200", any("φ1200" in n for n in names), str(names))

    # ---------- 10. token 刷新 ----------
    print("\n[10] token 刷新")
    r = client.post("/api/v1/auth/login", json={"username": "ouyuxin", "password": PASSWORD})
    refresh_token = r.json()["data"]["refresh_token"]
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    check("refresh 返回 200", r.status_code == 200, f"got {r.status_code}")
    check("刷新后拿到新 access_token", bool(r.json()["data"]["access_token"]))

    r = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    check("用 access_token 当 refresh 使用被拒绝", r.status_code == 401, f"got {r.status_code}")

    # ---------- 汇总 ----------
    print("\n" + "=" * 56)
    print(f"通过 {passed} 项，失败 {failed} 项")
    print("=" * 56)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
