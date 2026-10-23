"""创建“建设单位施工文件上传”展示测试项目。

登录账号：chenkaili / Tjad@2026
项目角色：建设单位
阶段起点：桩基施工
权限：仅本项目把建设单位在施工阶段提升为可上传，不改全局矩阵。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PROJECT_NAME = "建设单位桩基施工文件上传演示项目"
PASSWORD = "Tjad@2026"

PAYLOAD: dict[str, Any] = {
    "name": PROJECT_NAME,
    "short_name": "施工上传演示",
    "province": "浙江省",
    "city": "杭州市",
    "location": "杭州市滨江区",
    "project_type": "桩基工程",
    "scale_desc": "钻孔灌注桩 120 根（演示数据）",
    "description": "用于建设单位在桩基施工阶段上传、提交和发布工程文件的展示与测试。",
    "start_stage": "CONSTRUCTION",
    "owner_primary_construction": True,
}


def main() -> int:
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"username": "chenkaili", "password": PASSWORD})
    if r.status_code != 200:
        print(f"登录失败：{r.status_code} {r.text}")
        return 1
    headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    projects = client.get("/api/v1/projects", headers=headers).json().get("data") or []
    project = next((p for p in projects if p.get("name") == PROJECT_NAME), None)
    if project is None:
        r = client.post("/api/v1/projects", headers=headers, json=PAYLOAD)
        if r.status_code != 201:
            print(f"创建失败：{r.status_code} {r.text}")
            return 1
        project = r.json()["data"]

    detail = client.get(f"/api/v1/projects/{project['id']}", headers=headers).json()["data"]
    if detail.get("status") == "PREPARING":
        r = client.post(f"/api/v1/projects/{project['id']}/approve", headers=headers)
        if r.status_code != 200:
            print(f"审核失败：{r.status_code} {r.text}")
            return 1
        detail = r.json()["data"]
    me = client.get("/api/v1/auth/me", headers=headers).json()["data"]
    membership = next(x for x in me["memberships"] if x["project_id"] == project["id"])

    ok = (
        membership["unit_code"] == "OWNER"
        and "CONSTRUCTION" in membership["primary_stages"]
        and "EDIT" in membership["actions"]
        and detail["current_stage_code"] == "CONSTRUCTION"
    )
    print(f"项目编号：{project['project_no']}")
    print(f"项目名称：{project['name']}")
    print(f"项目 ID ：{project['id']}")
    print(f"登录账号：chenkaili / {PASSWORD}")
    print(f"参与单位：{membership['unit_label']}")
    print(f"施工阶段权限：{'可上传/提交/发布' if ok else '未正确配置'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
