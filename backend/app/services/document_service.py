"""文档服务: 上传入库主流水线。

阶段日志标签: [UPLOAD] [ROUTER] [PARSE] [SPLIT] [PERSIST] [EMBED] [INDEX]
完整覆盖: 双链路解析 -> 启发式路由 -> 保护式切分 -> 四层落库 -> 向量化 -> 索引重建。
"""
from __future__ import annotations

import os
import uuid

from sqlalchemy.orm import Session

from app.chunking.protected import build_chunks
from app.config import get_settings
from app.db.models import Chunk, ChunkVector, Document, Section
from app.logging_config import get_logger
from app.parsers.native import parse_native
from app.parsers.ocr import parse_ocr
from app.parsers.router import IMAGE_TYPES, choose_path
from app.retrieval.hybrid import get_retrieval_service
from app.vector.embeddings import EmbeddingService
from app.vector.milvus_client import get_vector_store

log = get_logger("doc", "PIPELINE")
_settings = get_settings()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
os.makedirs(os.path.abspath(UPLOAD_DIR), exist_ok=True)


def _detect_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext or "txt"


def process_upload(db: Session, filename: str, content: bytes) -> dict:
    """处理一次上传: 持久化 -> 解析 -> 切分 -> 入库 -> 向量化 -> 索引。"""
    file_type = _detect_type(filename)
    log.info(f"[UPLOAD] received {filename} ({file_type}, {len(content)} bytes)")

    # 落盘原文件
    safe_name = f"{uuid.uuid4().hex}_{filename}"
    disk_path = os.path.abspath(os.path.join(UPLOAD_DIR, safe_name))
    with open(disk_path, "wb") as f:
        f.write(content)

    # 启发式路由: 图像文件无需探测(必然无文本层), 其它类型先原生探测再决策
    probe = None
    if file_type in IMAGE_TYPES:
        path, reason = choose_path(file_type, None)
    else:
        probe = parse_native(disk_path, file_type)
        path, reason = choose_path(file_type, probe)
    log.info(f"[ROUTER] chose '{path}' path ({reason})")

    if path == "ocr":
        parsed = parse_ocr(disk_path, file_type)
        parse_path = "ocr"
    else:
        parsed = probe if probe is not None else parse_native(disk_path, file_type)
        parse_path = "native"
    log.info(
        f"[PARSE] tables={parsed.table_count} images={parsed.image_count} "
        f"density={parsed.text_density} pages={parsed.page_count}"
    )

    # 保护式切分
    plans = build_chunks(parsed)
    log.info(f"[SPLIT] produced {len(plans)} chunks (protected-aware)")

    # 四层落库
    doc = Document(
        filename=filename,
        title=os.path.splitext(filename)[0],
        file_type=file_type,
        file_size=len(content),
        status="processing",
        table_count=parsed.table_count,
        image_count=parsed.image_count,
        text_density=parsed.text_density,
        parse_path=parse_path,
        page_count=parsed.page_count,
    )
    db.add(doc)
    db.flush()  # 拿到 doc.id

    section = Section(document_id=doc.id, title=doc.title, level=1, order_idx=0)
    db.add(section)
    db.flush()

    chunk_rows: list[Chunk] = []
    for idx, plan in enumerate(plans):
        c = Chunk(
            document_id=doc.id,
            section_id=section.id,
            chunk_index=idx,
            content=plan.content,
            page=plan.page,
            has_table=plan.has_table,
            has_image=plan.has_image,
            protected=plan.protected,
            token_count=plan.token_count,
        )
        db.add(c)
        chunk_rows.append(c)
    db.flush()

    # 向量化
    emb = EmbeddingService()
    vs = get_vector_store()
    contents = [c.content for c in chunk_rows]
    vectors = emb.embed_batch(contents)
    for c, vec in zip(chunk_rows, vectors):
        ext_id = vs.upsert(c.id, vec, {"document_id": doc.id, "content": c.content[:200]})
        db.add(
            ChunkVector(
                chunk_id=c.id,
                store="milvus" if not _settings.mock_mode else "local",
                external_id=ext_id,
                model=_settings.embedding_model,
                dim=len(vec),
                status="active",
            )
        )
    log.info(f"[EMBED] embedded {len(vectors)} chunks")

    doc.status = "ready"
    db.commit()
    log.info(f"[PERSIST] document {doc.id} ready with {len(chunk_rows)} chunks")

    # 重建检索索引
    svc = get_retrieval_service()
    svc.build_index(db)
    log.info("[INDEX] retrieval index rebuilt")

    return {
        "document_id": doc.id,
        "filename": filename,
        "parse_path": parse_path,
        "chunk_count": len(chunk_rows),
        "table_count": parsed.table_count,
        "image_count": parsed.image_count,
        "status": doc.status,
    }


def delete_document(db: Session, document_id: int) -> bool:
    """文档级物理删除: 文档 + 段落 + chunk + 向量副本 + 向量库。

    数据库行删除由 ORM 级联 (cascade="all, delete-orphan") 处理;
    向量库与检索索引需手动同步清理。
    """
    from app.db.models import Chunk as C

    doc = db.get(Document, document_id)
    if not doc:
        return False
    log.info(f"[DELETE] physical delete document {document_id}")
    vs = get_vector_store()
    chunk_ids = [c.id for c in db.query(C.id).filter(C.document_id == document_id).all()]
    for cid in chunk_ids:
        vs.delete_by_chunk(cid)
    db.delete(doc)  # 级联删除 sections / chunks / chunk_vectors
    db.commit()
    get_retrieval_service().build_index(db)
    return True


def rebuild_index(db: Session, document_id: int | None = None) -> int:
    """索引重建: 重新嵌入并写回向量库 (可针对单文档或全量)。"""
    from app.db.models import Chunk as C

    log.info(f"[INDEX] rebuild requested (doc={document_id})")
    q = db.query(C).filter(C.is_deleted.is_(False))
    if document_id:
        q = q.filter(C.document_id == document_id)
    chunks = q.all()
    emb = EmbeddingService()
    vs = get_vector_store()
    if document_id:
        vs.delete_by_doc(document_id) if hasattr(vs, "delete_by_doc") else None
    vectors = emb.embed_batch([c.content for c in chunks])
    for c, vec in zip(chunks, vectors):
        vs.upsert(c.id, vec, {"document_id": c.document_id, "content": c.content[:200]})
    db.commit()
    n = get_retrieval_service().build_index(db)
    log.info(f"[INDEX] rebuild done ({n} chunks)")
    return n
