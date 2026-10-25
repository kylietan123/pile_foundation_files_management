"""文件存储服务 —— 内容寻址去重。

设计要点（对应《公共层契约》§5）：
1. **内容寻址**：file_id = sha256(content)，相同文件只存一份，数据库只记一份。
2. **原始文件不可变**：所有"编辑"都是新版本、新文件，绝不覆盖已有字节。
3. **下载走签名 URL**，不暴露真实存储路径；
   签名基于 SECRET_KEY 的 HMAC，且**绑定 file_id + 过期时间**，防止改参数拿别的文件。
4. ref_count 记录引用数，为后续垃圾回收预留（不在此处做删除）。

存储布局（相对 STORAGE_ROOT）：
    ab/cd/abcdef0123...          # 取 sha256 前两位/次两位分两级目录，避免单目录文件过多
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import mimetypes
import time
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.upload_formats import ALLOWED_EXT, BLOCKED_EXT
from app.models.document import FileObject


class StorageError(Exception):
    """存储层错误。"""


# ============================================================
# 路径与哈希
# ============================================================


def storage_root() -> Path:
    p = Path(settings.STORAGE_ROOT)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _storage_key(file_id: str, ext: str) -> str:
    """两级目录 + 文件名。避免单目录堆积几十万文件。"""
    return f"{file_id[:2]}/{file_id[2:4]}/{file_id}{ext}"


def _abs_path(storage_key: str) -> Path:
    root = storage_root().resolve()
    p = (root / storage_key).resolve()
    # 防目录穿越：确保解析后的路径仍在 storage_root 内
    if not str(p).startswith(str(root)):
        raise StorageError("非法的存储路径")
    return p


def _validate_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 1001, "message": "文件缺少扩展名，无法识别类型"},
        )
    if ext in BLOCKED_EXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 1001, "message": f"不允许上传 {ext} 类型的文件"},
        )
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": 1001,
                "message": f"不支持的文件类型 {ext}（设计文件请使用 pdf/dwg/docx/xlsx 等格式）",
            },
        )
    return ext


# ============================================================
# 写入
# ============================================================


async def save_upload(db: Session, upload: UploadFile, uploader_id: str | None) -> FileObject:
    """保存上传文件，返回 FileObject（已 flush 但未 commit）。

    相同内容重复上传时只增加 ref_count，不重复占用存储。
    """
    if not upload.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 1001, "message": "缺少文件名"},
        )

    ext = _validate_ext(upload.filename)
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    hasher = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0

    # 分块读取，边算哈希边累计，避免大文件把内存吃满
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "code": 1002,
                    "message": f"文件超过 {settings.MAX_UPLOAD_MB} MB 上限",
                },
            )
        hasher.update(chunk)
        chunks.append(chunk)

    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 1001, "message": "文件内容为空"},
        )

    file_id = hasher.hexdigest()

    # 已存在 → 去重，只加引用计数
    existing = db.get(FileObject, file_id)
    if existing is not None:
        existing.ref_count += 1
        db.flush()
        return existing

    storage_key = _storage_key(file_id, ext)
    path = _abs_path(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        for c in chunks:
            f.write(c)

    mime = upload.content_type or mimetypes.guess_type(upload.filename)[0] or "application/octet-stream"
    fo = FileObject(
        file_id=file_id,
        size=total,
        mime=mime,
        ext=ext,
        original_name=upload.filename,
        storage_key=storage_key,
        ref_count=1,
        created_by=uploader_id,
    )
    db.add(fo)
    db.flush()
    return fo


def save_bytes(
    db: Session,
    content: bytes,
    filename: str,
    mime: str | None = None,
    uploader_id: str | None = None,
) -> FileObject:
    """写入一段字节（用于测试与数据迁移，不经过 HTTP）。"""
    ext = _validate_ext(filename)
    file_id = hashlib.sha256(content).hexdigest()

    existing = db.get(FileObject, file_id)
    if existing is not None:
        existing.ref_count += 1
        db.flush()
        return existing

    storage_key = _storage_key(file_id, ext)
    path = _abs_path(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    fo = FileObject(
        file_id=file_id,
        size=len(content),
        mime=mime or mimetypes.guess_type(filename)[0] or "application/octet-stream",
        ext=ext,
        original_name=filename,
        storage_key=storage_key,
        ref_count=1,
        created_by=uploader_id,
    )
    db.add(fo)
    db.flush()
    return fo


def read_bytes(file_id: str) -> bytes:
    """按 file_id 读取文件内容。"""
    root = storage_root()
    # 由于不知道扩展名，遍历两级目录找匹配文件
    for p in (root / file_id[:2] / file_id[2:4]).glob(f"{file_id}.*"):
        return p.read_bytes()
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": 4004, "message": "文件内容不存在（可能已被清理）"},
    )


# ============================================================
# 签名下载 URL
# ============================================================


def _sign(file_id: str, expires_at: int, extra: str = "") -> str:
    msg = f"{file_id}:{expires_at}:{extra}".encode()
    raw = hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_download_token(file_id: str, version_id: str = "") -> dict:
    """生成短时效签名下载令牌。

    extra 里带 version_id，是为了让签名**绑定具体版本**：
    即使拿到 token，也不能拿去下载同一文件的其它版本。
    """
    ttl = settings.DOWNLOAD_URL_TTL_SECONDS
    expires_at = int(time.time()) + ttl
    return {
        "file_id": file_id,
        "version_id": version_id,
        "expires_at": expires_at,
        "signature": _sign(file_id, expires_at, version_id),
        "url": f"{settings.API_PREFIX}/files/{file_id}/download"
        f"?version_id={version_id}&expires_at={expires_at}&signature={_sign(file_id, expires_at, version_id)}",
        "ttl_seconds": ttl,
    }


def verify_download_token(file_id: str, version_id: str, expires_at: int, signature: str) -> None:
    """校验签名下载令牌。不通过抛 403。"""
    if expires_at < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3004, "message": "下载链接已过期，请重新获取"},
        )
    expected = _sign(file_id, expires_at, version_id)
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3004, "message": "下载链接签名无效"},
        )


# ============================================================
# 查询
# ============================================================


def get_file_object(db: Session, file_id: str) -> FileObject:
    fo = db.get(FileObject, file_id)
    if fo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "文件不存在"},
        )
    return fo


def storage_stats(db: Session) -> dict:
    """存储统计，供运维查看去重效果。"""
    rows = db.execute(select(FileObject)).scalars().all()
    total_size = sum(r.size for r in rows)
    total_refs = sum(r.ref_count for r in rows)
    return {
        "file_count": len(rows),
        "total_bytes": total_size,
        "total_refs": total_refs,
        "dedup_saved_bytes": total_size * (total_refs - len(rows)) if total_refs > len(rows) else 0,
    }
