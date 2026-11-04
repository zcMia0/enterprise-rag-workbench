"""Chunk 服务: 可观测 / 可编辑 / 可删除。

编辑后重新向量化并刷新检索索引; 删除为软删除 (is_deleted),
同步从向量库与 BM25 移除, 保证检索不命中已删块。
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Chunk, ChunkVector
from app.logging_config import get_logger
from app.retrieval.hybrid import get_retrieval_service
from app.vector.embeddings import EmbeddingService
from app.vector.milvus_client import get_vector_store

log = get_logger("chunk", "OPS")


def list_chunks(db: Session, document_id: int | None, page: int, size: int) -> dict:
    q = db.query(Chunk).filter(Chunk.is_deleted.is_(False))
    if document_id:
        q = q.filter(Chunk.document_id == document_id)
    total = q.with_entities(func.count()).scalar() or 0
    rows = (
        q.order_by(Chunk.document_id, Chunk.chunk_index)
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    items = [
        {
            "chunk_id": c.id,
            "document_id": c.document_id,
            "chunk_index": c.chunk_index,
            "page": c.page,
            "has_table": c.has_table,
            "has_image": c.has_image,
            "protected": c.protected,
            "token_count": c.token_count,
            "content": c.content,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in rows
    ]
    return {"total": total, "page": page, "size": size, "items": items}


def get_chunk(db: Session, chunk_id: int) -> dict | None:
    c = db.get(Chunk, chunk_id)
    if not c or c.is_deleted:
        return None
    return {
        "chunk_id": c.id,
        "document_id": c.document_id,
        "chunk_index": c.chunk_index,
        "page": c.page,
        "has_table": c.has_table,
        "has_image": c.has_image,
        "protected": c.protected,
        "token_count": c.token_count,
        "content": c.content,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def update_chunk(db: Session, chunk_id: int, content: str) -> dict | None:
    """编辑 chunk 内容, 重新向量化并刷新索引。"""
    c = db.get(Chunk, chunk_id)
    if not c or c.is_deleted:
        return None
    c.content = content
    c.token_count = max(1, len(content) // 2)
    db.flush()
    # 重新向量化
    emb = EmbeddingService()
    vs = get_vector_store()
    vec = emb.embed(content)
    ext_id = vs.upsert(c.id, vec, {"document_id": c.document_id, "content": content[:200]})
    cv = db.query(ChunkVector).filter(ChunkVector.chunk_id == c.id).first()
    if cv:
        cv.external_id = ext_id
        cv.dim = len(vec)
        cv.model = emb_mode()
    db.commit()
    get_retrieval_service().index_chunk(
        c.id, content, {"document_id": c.document_id, "filename": "", "page": c.page, "content": content}
    )
    log.info(f"[OPS] chunk {chunk_id} edited & re-embedded")
    return get_chunk(db, chunk_id)


def delete_chunk(db: Session, chunk_id: int) -> bool:
    """软删除 chunk, 同步清理向量与索引。"""
    c = db.get(Chunk, chunk_id)
    if not c or c.is_deleted:
        return False
    c.is_deleted = True
    db.query(ChunkVector).filter(ChunkVector.chunk_id == c.id).delete()
    db.commit()
    vs = get_vector_store()
    vs.delete_by_chunk(chunk_id)
    get_retrieval_service().remove_chunk(chunk_id)
    log.info(f"[OPS] chunk {chunk_id} soft-deleted")
    return True


def emb_mode() -> str:
    from app.config import get_settings

    return get_settings().embedding_model
