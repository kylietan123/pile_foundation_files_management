"""实测演示文件能不能真的下载下来，以及**下载到的文件能不能打开**。

这验证的是两个真实踩过的 bug：
  1. 种子只写数据库记录、不落盘，且自编的 storage_key 与读取规则不一致
     → 下载一律 404；
  2. 后来落盘了，但把一句中文 UTF-8 文本标成 application/pdf 存进去
     → 能下载、字节数不为 0，可用任何阅读器都打不开（演示时"看不了文件"）。

所以这里不只检查"下载成功"，还检查**内容是不是合规的 PDF**
（`%PDF-` 开头、`%%EOF` 结尾、xref 能对上）。
"""
from __future__ import annotations

import io
import re
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


def pdf_ok(data: bytes) -> tuple[bool, str]:
    """结构校验：头/尾/startxref 指向 xref/每个对象偏移正确/流长度一致。"""
    if not data.startswith(b"%PDF-"):
        return False, f"不是 PDF 头：{data[:16]!r}"
    if not data.rstrip().endswith(b"%%EOF"):
        return False, "缺 %%EOF"
    m = re.search(rb"startxref\s+(\d+)\s+%%EOF", data)
    if not m:
        return False, "缺 startxref"
    pos = int(m.group(1))
    if data[pos:pos + 4] != b"xref":
        return False, f"startxref={pos} 未指向 xref"
    tbl = data[pos:].split(b"trailer")[0].decode("latin-1").splitlines()
    count = int(tbl[1].split()[1])
    entries = [ln for ln in tbl[2:] if ln.strip()]
    if len(entries) != count:
        return False, f"xref 条目 {len(entries)} != {count}"
    for i, ln in enumerate(entries):
        if i == 0:
            continue
        off = int(ln.split()[0])
        if data[off:off + len(f"{i} 0 obj")] != f"{i} 0 obj".encode():
            return False, f"对象 {i} 偏移 {off} 不对"
    for mm in re.finditer(rb"<< /Length (\d+) >>\s*stream\n", data):
        declared = int(mm.group(1))
        start = mm.end()
        end = data.find(b"\nendstream", start)
        if declared != end - start:
            return False, f"流长度 {declared} != {end - start}"
    return True, ""


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
    body = r2.content
    chk(f"{item['doc_no']} {item['current_version_no']} 下载成功",
        r2.status_code == 200 and len(body) > 0,
        f"status={r2.status_code} len={len(body)} {r2.text[:120] if r2.status_code != 200 else ''}")
    if r2.status_code != 200:
        continue

    # 关键：内容必须是能打开的 PDF，而不是一段被标成 pdf 的文本
    good, why = pdf_ok(body)
    chk(f"{item['doc_no']} 下载到的内容是合规 PDF", good, why)
    print(f"          {len(body)} 字节，头 {body[:8]!r}")

    # 预览场景：默认不该强制另存为，否则 window.open 打开是空白页
    disp = r2.headers.get("content-disposition", "")
    chk(f"{item['doc_no']} 默认 inline 预览", disp.startswith("inline"), disp[:80])

    # ?download=1 时应强制另存为
    r3 = c.get(path + ("&download=1" if "?" in path else "?download=1"))
    chk(f"{item['doc_no']} download=1 时强制另存为",
        r3.headers.get("content-disposition", "").startswith("attachment"),
        r3.headers.get("content-disposition", "")[:80])

print("\n" + "=" * 68)
print(f"通过 {ok} 项，失败 {bad} 项")
print("=" * 68)
sys.exit(0 if bad == 0 else 1)
