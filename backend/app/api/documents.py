"""文档管理路由: 列表 / 详情 / 物理删除 / 单文档索引重建。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document
from app.db.postgres import get_db
from app.schemas.rag import DocumentOut
from app.services.document_service import delete_document, rebuild_index

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
def list_documents(page: int = 1, size: int = 50, db: Session = Depends(get_db)):
    rows = (
        db.query(Document)
        .order_by(Document.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    out = []
    for d in rows:
        cnt = (
            db.query(func.count(Chunk.id))
            .filter(Chunk.document_id == d.id, Chunk.is_deleted.is_(False))
            .scalar()
            or 0
        )
        out.append(
            DocumentOut(
                id=d.id,
                filename=d.filename,
                file_type=d.file_type,
                status=d.status,
                table_count=d.table_count,
                image_count=d.image_count,
                text_density=d.text_density,
                parse_path=d.parse_path,
                page_count=d.page_count,
                chunk_count=cnt,
                created_at=d.created_at.isoformat() if d.created_at else None,
            )
        )
    return out


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if not d:
        raise HTTPException(status_code=404, detail="文档不存在")
    cnt = (
        db.query(func.count(Chunk.id))
        .filter(Chunk.document_id == d.id, Chunk.is_deleted.is_(False))
        .scalar()
        or 0
    )
    return DocumentOut(
        id=d.id, filename=d.filename, file_type=d.file_type, status=d.status,
        table_count=d.table_count, image_count=d.image_count,
        text_density=d.text_density, parse_path=d.parse_path,
        page_count=d.page_count, chunk_count=cnt,
        created_at=d.created_at.isoformat() if d.created_at else None,
    )


@router.delete("/{document_id}")
def remove_document(document_id: int, db: Session = Depends(get_db)):
    if not delete_document(db, document_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"ok": True, "document_id": document_id}


@router.post("/{document_id}/rebuild")
def rebuild_document_index(document_id: int, db: Session = Depends(get_db)):
    """单文档索引重建。"""
    if not db.get(Document, document_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    n = rebuild_index(db, document_id)
    return {"ok": True, "document_id": document_id, "indexed_chunks": n}
