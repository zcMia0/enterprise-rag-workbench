"""上传入库路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.schemas.rag import UploadResult
from app.services.document_service import process_upload

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("", response_model=UploadResult)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """上传文档并触发双链路解析 -> 切分 -> 向量化 -> 索引。"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="空文件")
    try:
        result = process_upload(db, file.filename or "untitled", content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"处理失败: {exc}") from exc
    return UploadResult(**result)
