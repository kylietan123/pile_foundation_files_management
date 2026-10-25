"""
全局配置。

所有可调项集中在这里，通过 .env 覆盖。
换数据库、换 JWT 密钥、换 LLM 提供方都只改这里，不改业务代码。
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
APP_DIR = BACKEND_DIR / "app"
STORAGE_DIR = BACKEND_DIR / "storage"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- 应用 ----------
    APP_NAME: str = "桩基工程全生命周期管理平台"
    APP_ENV: str = "dev"                 # dev / test / prod
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # ---------- 数据库 ----------
    # 开发期用 SQLite，切换 PostgreSQL 只改这一行：
    #   postgresql+psycopg://user:pass@host:5432/pile_lcm
    DATABASE_URL: str = f"sqlite:///{(BACKEND_DIR / 'pile_lcm.db').as_posix()}"
    SQL_ECHO: bool = False

    # ---------- 认证 ----------
    # 生产环境必须通过 .env 覆盖，禁止使用默认值
    SECRET_KEY: str = "DEV-ONLY-CHANGE-ME-before-deploy"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8       # 8 小时
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    BCRYPT_ROUNDS: int = 12                          # 测试环境可降到 4 提速

    # ---------- 文件存储 ----------
    STORAGE_ROOT: str = str(STORAGE_DIR)
    DOWNLOAD_URL_TTL_SECONDS: int = 300              # 签名下载链接 5 分钟有效期
    MAX_UPLOAD_MB: int = 500

    # ---------- 分页 ----------
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 200

    # ---------- AI（第 8 周启用，先留配置位）----------
    LLM_PROVIDER: str = "none"           # none / cloud / local
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    AI_ALLOW_CROSS_PROJECT: bool = False  # 内部试用期禁止跨项目检索
    AI_LOG_RETENTION_DAYS: int = 90
    KNOWLEDGE_CHUNK_MAX_TOKENS: int = 500


settings = Settings()

# 确保存储目录存在
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
