"""密码哈希与 JWT。

**刻意不依赖 passlib / python-jose / cryptography**，全部用标准库实现：

理由有三：
1. 减少依赖 = 减少另外两位的环境配置成本（cryptography 在 Windows 上安装很慢）。
2. HS256 的 JWT 实现只有 30 行，逻辑完全可审计，避免黑盒。
3. 标准库 hmac.compare_digest 提供常数时间比较，防时序攻击。

密码哈希用 PBKDF2-HMAC-SHA256（标准库 hashlib.pbkdf2_hmac），
迭代次数可配置。这是 NIST 认可的方案。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.config import settings

# ============================================================
# 密码哈希
# ============================================================

PBKDF2_ITERATIONS = 260_000
SALT_BYTES = 16


def hash_password(password: str) -> str:
    """生成密码哈希。格式：pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>"""
    salt = secrets.token_bytes(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(dk).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    """校验密码。使用常数时间比较，防时序攻击。"""
    try:
        algo, iters_s, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters_s))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# ============================================================
# JWT（HS256）
# ============================================================


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def _sign(msg: bytes) -> bytes:
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).digest()


def create_token(
    subject: str,
    token_type: str = "access",
    expires_in: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """生成 JWT。

    token_type: access / refresh
    """
    now = int(time.time())
    if expires_in is None:
        expires_in = (
            settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            if token_type == "access"
            else settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
        )

    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_in,
        "jti": secrets.token_hex(8),
    }
    if extra_claims:
        payload.update(extra_claims)

    seg_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    seg_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{seg_header}.{seg_payload}".encode("ascii")
    signature = _b64url_encode(_sign(signing_input))
    return f"{seg_header}.{seg_payload}.{signature}"


def decode_token(token: str) -> dict[str, Any]:
    """解析并校验 JWT。失败抛 ValueError。

    校验项：签名、exp、结构。
    """
    try:
        seg_header, seg_payload, seg_sig = token.split(".")
    except ValueError as exc:
        raise ValueError("token 格式错误") from exc

    signing_input = f"{seg_header}.{seg_payload}".encode("ascii")
    expected_sig = _sign(signing_input)
    try:
        actual_sig = _b64url_decode(seg_sig)
    except Exception as exc:
        raise ValueError("签名编码错误") from exc

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("签名校验失败")

    try:
        payload = json.loads(_b64url_decode(seg_payload))
    except Exception as exc:
        raise ValueError("payload 解析失败") from exc

    exp = payload.get("exp")
    if exp is None or int(exp) < int(time.time()):
        raise ValueError("token 已过期")

    return payload


def create_access_token(
    user_id: str,
    token_version: int = 0,
    extra: dict[str, Any] | None = None,
) -> str:
    claims: dict[str, Any] = {"ver": int(token_version or 0)}
    if extra:
        claims.update(extra)
    return create_token(user_id, "access", extra_claims=claims)


def create_refresh_token(user_id: str, token_version: int = 0) -> str:
    return create_token(
        user_id,
        "refresh",
        extra_claims={"ver": int(token_version or 0)},
    )
