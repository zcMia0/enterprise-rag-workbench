"""混合检索编排: 向量(Milvus) + BM25 + RRF 融合 + Prefetch 预检索。

链路:
  query
    ├─ Embedding -> VectorStore.search (向量分)
    └─ BM25.search (词面分)
         │
         └─ RRF 融合 -> 排序后的证据片段 (带 vector_score / bm25_score / fused_score)

Prefetch (预检索): 在模型生成之前先完成证据检索, 把高相关片段注入上下文,
强制 Agent 基于知识库作答, 防止其绕开知识库直接生成 (见 agent 层证据裁判)。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.retrieval.bm25 import BM25
from app.retrieval.rrf import rrf_fuse
from app.vector.embeddings import EmbeddingService
from app.vector.milvus_client import get_vector_store

log = get_logger("retriever", "HYBRID")

_settings = get_settings()


@dataclass
class RetrievalHit:
    chunk_id: int
    document_id: int
    filename: str
    page: int
    content: str
    vector_score: float = 0.0
    bm25_score: float = 0.0
    fused_score: float = 0.0
    source: str = "hybrid"


_retrieval_service: "RetrievalService | None" = None


def get_retrieval_service() -> "RetrievalService":
    """全局检索服务单例 (索引在文档变更后重建复用)。"""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service


class RetrievalService:
    def __init__(self) -> None:
        self.bm25 = BM25()
        self.embeddings = EmbeddingService()
        self.vs = get_vector_store()
        self.meta: dict[int, dict] = {}  # chunk_id -> {document_id, filename, page, content}
        self._built = False

    def build_index(self, db: Session) -> int:
        """从 DB 加载全部未删除 chunk, 重建 BM25 与内存 meta 映射。"""
        from app.db.models import Chunk, Document

        rows = (
            db.query(Chunk, Document.filename)
            .join(Document, Chunk.document_id == Document.id)
            .filter(Chunk.is_deleted.is_(False))
            .all()
        )
        self.bm25 = BM25()
        self.meta = {}
        for chunk, filename in rows:
            self.bm25.index(chunk.id, chunk.content)
            self.meta[chunk.id] = {
                "document_id": chunk.document_id,
                "filename": filename,
                "page": chunk.page,
                "content": chunk.content,
            }
        self.bm25.build()
        self._built = True
        log.info(f"retrieval index rebuilt ({len(self.meta)} chunks)")
        return len(self.meta)

    def retrieve(
        self, db: Session, query: str, top_k: int | None = None, filter_doc_ids=None
    ) -> list[RetrievalHit]:
        """Prefetch + 混合检索。返回带多分数的证据片段。"""
        top_k = top_k or _settings.vector_top_k
        log.info(f"[PREFETCH] evidence retrieval started for query: {query[:40]!r}")

        if not self._built:
            self.build_index(db)

        # 1) 向量检索
        q_vec = self.embeddings.embed(query)
        vec_res = self.vs.search(q_vec, _settings.hybrid_fetch_k, filter_doc_ids)
        for r in vec_res:
            r["source"] = "vector"

        # 2) BM25 检索
        bm_res = self.bm25.search(query, _settings.bm25_top_k)
        for r in bm_res:
            r["source"] = "bm25"

        # 3) RRF 融合
        fused = rrf_fuse([vec_res, bm_res])
        fused = fused[: max(top_k, _settings.hybrid_fetch_k)]

        # 4) 组装命中 (回填 meta + 各来源分)
        hits: list[RetrievalHit] = []
        vec_map = {r["chunk_id"]: r["score"] for r in vec_res}
        bm_map = {r["chunk_id"]: r["score"] for r in bm_res}
        for f in fused:
            cid = f["chunk_id"]
            m = self.meta.get(cid)
            if not m:
                continue
            hits.append(
                RetrievalHit(
                    chunk_id=cid,
                    document_id=m["document_id"],
                    filename=m["filename"],
                    page=m["page"],
                    content=m["content"],
                    vector_score=round(vec_map.get(cid, 0.0), 4),
                    bm25_score=round(bm_map.get(cid, 0.0), 4),
                    fused_score=round(f["fused_score"], 4),
                    source="hybrid",
                )
            )
        log.info(f"[PREFETCH] retrieved {len(hits)} evidence hits")
        return hits[:top_k]

    def index_chunk(self, chunk_id: int, content: str, meta: dict) -> None:
        """单条 chunk 入库后增量更新索引。"""
        self.bm25.index(chunk_id, content)
        self.bm25.build()
        self.meta[chunk_id] = meta
        self._built = True

    def remove_chunk(self, chunk_id: int) -> None:
        self.bm25.remove(chunk_id)
        self.meta.pop(chunk_id, None)
        self._built = True
