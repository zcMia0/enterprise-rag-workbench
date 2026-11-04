"""Chunk 管理路由: 列表 / 详情 / 编辑 / 删除。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.schemas.rag import ChunkOut, ChunkPage, ChunkUpdate
from app.services import chunk_service as cs

router = APIRouter(prefix="/api/chunks", tags=["chunks"])


@router.get("", response_model=ChunkPage)
def list_chunks(page: int = 1, size: int = 20, document_id: int | None = None,
                db: Session = Depends(get_db)):
    return cs.list_chunks(db, document_id, page, size)


@router.get("/{chunk_id}", response_model=ChunkOut)
def get_chunk(chunk_id: int, db: Session = Depends(get_db)):
    c = cs.get_chunk(db, chunk_id)
    if not c:
        raise HTTPException(status_code=404, detail="Chunk 不存在")
    return ChunkOut(**c)


@router.put("/{chunk_id}", response_model=ChunkOut)
def update_chunk(chunk_id: int, body: ChunkUpdate, db: Session = Depends(get_db)):
    c = cs.update_chunk(db, chunk_id, body.content)
    if not c:
        raise HTTPException(status_code=404, detail="Chunk 不存在")
    return ChunkOut(**c)


@router.delete("/{chunk_id}")
def delete_chunk(chunk_id: int, db: Session = Depends(get_db)):
    if not cs.delete_chunk(db, chunk_id):
        raise HTTPException(status_code=404, detail="Chunk 不存在")
    return {"ok": True, "chunk_id": chunk_id}
