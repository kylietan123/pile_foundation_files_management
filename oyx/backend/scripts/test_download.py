"""实测演示文件能不能真的下载下来。

这验证的是刚修的那个 bug：种子只写数据库记录、不落盘，
而且自编的 storage_key 与读取规则不一致 → 下载一律 404。
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
ok = 0
bad = 0


def chk(desc, cond, extra=""):
    global ok, bad
    if cond:
        ok += 1
        print(f"  [OK]   {desc}")
    else:
        bad += 1
        print(f"  [FAIL] {desc}  {extra}")


def login(u):
    r = c.post("/api/v1/auth/login", json={"username": u, "password": "Tjad@2026"})
    return {"Authorization": "Bearer " + r.json()["data"]["access_token"]}


h = login("ouyuxin")
pid = next(p for p in c.get("/api/v1/projects", headers=h).json()["data"]
           if "杭州" in p["name"])["id"]

print("=" * 68)
print("演示文件下载验证")
print("=" * 68)

# 取台账里的已发布文件（这些"下载"按钮应该真的能下）
led = c.get(f"/api/v1/projects/{pid}/ledger", headers=h).json()["data"]
withver = [i for i in led["items"] if i.get("current_version_no")]
print(f"\n台账里有已发布版本的文件：{len(withver)} 份")
chk("台账里存在已发布文件（否则没法验证）", bool(withver))

for item in withver:
    # 找到当前版本的 version_id
    vs = c.get(f"/api/v1/documents/{item['document_id']}/versions", headers=h).json()["data"]
    cur = next((v for v in vs if v["version_no"] == item["current_version_no"]), None)
    if cur is None:
        chk(f"{item['doc_no']} 能找到当前版本", False)
        continue

    # 取下载令牌
    r = c.get(f"/api/v1/versions/{cur['id']}/download-token", headers=h)
    if r.status_code != 200:
        chk(f"{item['doc_no']} 取下载令牌", False, r.text[:160])
        continue
    tok = r.json()["data"]

    # 用令牌下载（签名 URL 走同一个 client）
    path = tok["url"]
    if path.startswith("http"):
        from urllib.parse import urlparse
        path = urlparse(path).path + ("?" + urlparse(tok["url"]).query if urlparse(tok["url"]).query else "")
    r2 = c.get(path)
    chk(f"{item['doc_no']} {item['current_version_no']} 下载成功",
        r2.status_code == 200 and len(r2.content) > 0,
        f"status={r2.status_code} len={len(r2.content)} {r2.text[:120] if r2.status_code != 200 else ''}")
    if r2.status_code == 200:
        print(f"          内容 {len(r2.content)} 字节，前 40 字节：{r2.content[:40]!r}")

print("\n" + "=" * 68)
print(f"通过 {ok} 项，失败 {bad} 项")
print("=" * 68)
sys.exit(0 if bad == 0 else 1)
