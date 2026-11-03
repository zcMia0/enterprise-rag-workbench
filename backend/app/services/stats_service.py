"""统计服务: 总览看板数据 + 后台服务状态。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Chunk, Document, QALog
from app.db.postgres import get_engine
from app.db.redis_client import redis_client
from app.logging_config import get_logger
from app.vector.milvus_client import get_vector_store

log = get_logger("stats", "OVERVIEW")
_settings = get_settings()


def overview(db: Session) -> dict:
    doc_count = db.query(func.count(Document.id)).scalar() or 0
    chunk_count = (
        db.query(func.count(Chunk.id)).filter(Chunk.is_deleted.is_(False)).scalar() or 0
    )
    session_count = db.query(func.count(func.distinct(QALog.thread_id))).scalar() or 0

    services = _service_health()
    return {
        "documents": doc_count,
        "chunks": chunk_count,
        "agent_sessions": session_count,
        "services": services,
        "mock_mode": _settings.mock_mode,
    }


def _service_health() -> dict:
    # PostgreSQL / SQLite 兜底
    pg_ok = False
    using_sqlite = _settings.mock_mode
    try:
        with get_engine().connect() as conn:
            conn.execute(select(1))
        pg_ok = True
    except Exception:  # noqa: BLE001
        pg_ok = False

    # Redis (真实 or 内存降级)
    redis_ok = redis_client.ping()
    redis_label = "online" if (redis_ok and not redis_client.using_mock) else "offline(mock)"

    # Milvus / 本地向量
    milvus_ok = False
    try:
        vs = get_vector_store()
        _ = vs.count()
        milvus_ok = True
    except Exception:  # noqa: BLE001
        milvus_ok = False

    return {
        "postgres": ("sqlite(local)" if using_sqlite else ("online" if pg_ok else "offline")),
        "redis": redis_label,
        "milvus": "online" if (milvus_ok and not _settings.mock_mode) else "local/mock",
        "db_backend": "sqlite" if using_sqlite else "postgres",
    }
