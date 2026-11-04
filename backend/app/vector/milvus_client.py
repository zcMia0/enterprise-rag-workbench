"""向量库抽象: Milvus 真实客户端 + 本地文件降级。

设计: VectorStore 统一接口 (upsert / search / delete_by_chunk / rebuild)。
- MilvusVectorStore: 真实接入 docker 中的 Milvus (standalone)。
- LocalVectorStore: 用本地 JSONL 文件持久化 (chunk_id -> embedding), 余弦检索,
  用于 Mock 模式或无 Milvus 环境, 保证检索链路端到端可跑。
"""
from __future__ import annotations

import json
import os
import threading

from app.config import get_settings
from app.logging_config import get_logger
from app.vector.embeddings import cosine

log = get_logger("vector", "VSTORE")

_settings = get_settings()
_STORE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "vectors.jsonl")


class VectorStore:
    """统一接口。"""

    def upsert(self, chunk_id: int, vector: list[float], meta: dict) -> str:
        raise NotImplementedError

    def search(self, vector: list[float], top_k: int, filter_doc_ids=None) -> list[dict]:
        raise NotImplementedError

    def delete_by_chunk(self, chunk_id: int) -> None:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError


class LocalVectorStore(VectorStore):
    """本地文件向量库 (Mock 默认), 持久化为 JSONL。"""

    def __init__(self, path: str = _STORE_PATH) -> None:
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        # 可重入锁: upsert/delete 持锁后会调用 _persist(), _persist 内部也加锁
        self._mu = threading.RLock()
        self._data: dict[int, dict] = {}
        self._load()
        log.info(f"local vector store ready ({len(self._data)} vectors) @ {self.path}")

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        with self._mu:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    self._data[row["chunk_id"]] = row

    def _persist(self) -> None:
        with self._mu:
            with open(self.path, "w", encoding="utf-8") as f:
                for row in self._data.values():
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def upsert(self, chunk_id: int, vector: list[float], meta: dict) -> str:
        ext_id = f"local-{chunk_id}"
        with self._mu:
            self._data[chunk_id] = {
                "chunk_id": chunk_id,
                "vector": vector,
                "meta": meta,
                "external_id": ext_id,
            }
            self._persist()
        return ext_id

    def search(self, vector: list[float], top_k: int, filter_doc_ids=None) -> list[dict]:
        with self._mu:
            rows = list(self._data.values())
        results = []
        for row in rows:
            if filter_doc_ids is not None and row["meta"].get("document_id") not in filter_doc_ids:
                continue
            score = cosine(vector, row["vector"])
            results.append(
                {
                    "chunk_id": row["chunk_id"],
                    "score": score,
                    "meta": row["meta"],
                    "external_id": row["external_id"],
                }
            )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete_by_chunk(self, chunk_id: int) -> None:
        with self._mu:
            if chunk_id in self._data:
                del self._data[chunk_id]
                self._persist()

    def delete_by_doc(self, document_id: int) -> None:
        with self._mu:
            to_del = [
                cid
                for cid, row in self._data.items()
                if row["meta"].get("document_id") == document_id
            ]
            for cid in to_del:
                del self._data[cid]
            self._persist()

    def count(self) -> int:
        with self._mu:
            return len(self._data)


class MilvusVectorStore(VectorStore):
    """真实 Milvus 客户端 (需 docker 中 Milvus 在线)。"""

    def __init__(self) -> None:
        from pymilvus import (
            Collection,
            CollectionSchema,
            DataType,
            FieldSchema,
            connections,
            utility,
        )

        self._mod = __import__("pymilvus", fromlist=["connections"])
        connections.connect(
            alias="default",
            host=_settings.milvus_host,
            port=_settings.milvus_port,
        )
        self.dim = _settings.embedding_dim
        self.collection_name = _settings.milvus_collection
        fields = [
            FieldSchema(name="chunk_id", dtype=DataType.Int64, is_primary=True),
            FieldSchema(name="document_id", dtype=DataType.Int64),
            FieldSchema(name="embedding", dtype=DataType.FloatVector, dim=self.dim),
            FieldSchema(name="content", dtype=DataType.VarChar, max_length=65535),
        ]
        schema = CollectionSchema(fields, description="rag chunks")
        if not utility.has_collection(self.collection_name):
            Collection(self.collection_name, schema, consistency_level="Bounded")
        self.collection: Collection = Collection(self.collection_name)
        self.collection.load()
        log.info(f"milvus connected, collection={self.collection_name}")

    def upsert(self, chunk_id: int, vector: list[float], meta: dict) -> str:
        self.collection.delete(expr=f"chunk_id in [{chunk_id}]")
        self.collection.insert(
            [
                [chunk_id],
                [meta.get("document_id", 0)],
                [vector],
                [meta.get("content", "")[:65535]],
            ]
        )
        self.collection.flush()
        return f"milvus-{chunk_id}"

    def search(self, vector: list[float], top_k: int, filter_doc_ids=None) -> list[dict]:
        expr = None
        if filter_doc_ids:
            expr = f"document_id in {list(filter_doc_ids)}"
        res = self.collection.search(
            data=[vector],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=top_k,
            expr=expr,
            output_fields=["chunk_id", "document_id", "content"],
        )
        out = []
        for hits in res:
            for hit in hits:
                out.append(
                    {
                        "chunk_id": hit.entity.get("chunk_id"),
                        "score": hit.score,
                        "meta": {
                            "document_id": hit.entity.get("document_id"),
                            "content": hit.entity.get("content"),
                        },
                        "external_id": f"milvus-{hit.entity.get('chunk_id')}",
                    }
                )
        return out

    def delete_by_chunk(self, chunk_id: int) -> None:
        self.collection.delete(expr=f"chunk_id in [{chunk_id}]")
        self.collection.flush()

    def count(self) -> int:
        return self.collection.num_entities


def build_vector_store() -> VectorStore:
    """工厂: Mock 模式或无 Milvus 时返回本地库, 否则真实 Milvus。"""
    if _settings.mock_mode:
        return LocalVectorStore()
    try:
        return MilvusVectorStore()
    except Exception as exc:  # noqa: BLE001
        log.warning(f"milvus init failed ({exc}); local fallback")
        return LocalVectorStore()


# 全局单例 (启动时构建)
vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global vector_store
    if vector_store is None:
        vector_store = build_vector_store()
    return vector_store
