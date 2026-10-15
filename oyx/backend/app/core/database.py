"""数据库引擎与会话。

设计要点：
1. 开发期 SQLite，生产切 PostgreSQL —— 只改 DATABASE_URL，不动模型代码。
2. 因此**刻意规避 PostgreSQL 专有特性**（JSONB / ARRAY / CITEXT）。
   需要 JSON 时统一用 sqlalchemy.JSON，需要大文本统一用 Text。
3. 主键统一用字符串 UUID（见 models/base.py），不用自增整数，
   便于多阶段数据合并与离线生成。
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# SQLite 需要允许跨线程（FastAPI 的依赖注入会切换线程）
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


# SQLite 默认不强制外键约束，显式打开，否则外键形同虚设
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
