"""数据库引擎与会话管理。

支持两种后端:
- PostgreSQL (docker-compose 提供, 生产/标准形态)
- SQLite 兜底 (Mock 模式或本机无 PG 时, 保证 `python main.py` 直接能跑)

连接失败时的策略:
- 若配置的是 PG 且连接不上, 自动回退 SQLite 并打印醒目警告, 不让项目因依赖未起而崩溃。
"""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings, resolve_db_url
from app.logging_config import get_logger

log = get_logger("db", "INIT")

_settings = get_settings()
DB_URL = resolve_db_url(_settings)

_connect_args: dict = {}
if DB_URL.startswith("sqlite"):
    # SQLite 需允许跨线程( FastAPI 线程池 ) 与单文件目录创建
    os.makedirs(os.path.dirname(DB_URL.replace("sqlite:///", "")), exist_ok=True)
    _connect_args = {"check_same_thread": False}

try:
    _engine = create_engine(DB_URL, connect_args=_connect_args, pool_pre_ping=True)
    # 探活: 真正连一次
    with _engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    log.info(f"database connected -> {DB_URL.split('@')[-1] if '@' in DB_URL else DB_URL}")
except Exception as exc:  # noqa: BLE001 - 兜底回退是预期行为
    log.warning(f"primary db unreachable ({exc}); falling back to SQLite dev db")
    DB_URL = _settings.sqlite_fallback
    os.makedirs(os.path.dirname(DB_URL.replace("sqlite:///", "")), exist_ok=True)
    _engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """建表 (幂等)。Mock/SQLite 同样适用。"""
    from app.db import models  # noqa: F401 - 确保模型注册

    models.Base.metadata.create_all(_engine)
    log.info("tables ensured (create_all)")


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖: 请求级会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_engine():
    return _engine
