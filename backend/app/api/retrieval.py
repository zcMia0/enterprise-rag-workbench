"""检索调试路由: 展示向量分 / BM25 分 / 融合分。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.retrieval.hybrid import get_retrieval_service
from app.schemas.rag import RetrievalHitOut, RetrievalRequest

router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])


@router.post("/debug", response_model=list[RetrievalHitOut])
def retrieval_debug(body: RetrievalRequest, db: Session = Depends(get_db)):
    """调试检索: 返回带多分数的证据片段, 用于验证混合检索效果。"""
    svc = get_retrieval_service()
    filter_ids = {body.document_id} if body.document_id else None
    hits = svc.retrieve(db, body.query, top_k=body.top_k, filter_doc_ids=filter_ids)
    return [
        RetrievalHitOut(
            chunk_id=h.chunk_id,
            document_id=h.document_id,
            filename=h.filename,
            page=h.page,
            content=h.content[:400],
            vector_score=h.vector_score,
            bm25_score=h.bm25_score,
            fused_score=h.fused_score,
            source=h.source,
        )
        for h in hits
    ]
