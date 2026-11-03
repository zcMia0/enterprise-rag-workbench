"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------- 文档 ----------------
class DocumentOut(BaseModel):
    id: int
    filename: str
    file_type: str
    status: str
    table_count: int = 0
    image_count: int = 0
    text_density: float | None = None
    parse_path: str = "native"
    page_count: int = 0
    chunk_count: int = 0
    created_at: str | None = None


class UploadResult(BaseModel):
    document_id: int
    filename: str
    parse_path: str
    chunk_count: int
    table_count: int
    image_count: int
    status: str


# ---------------- Chunk ----------------
class ChunkUpdate(BaseModel):
    content: str = Field(..., min_length=1)


class ChunkOut(BaseModel):
    chunk_id: int
    document_id: int
    chunk_index: int
    page: int
    has_table: bool
    has_image: bool
    protected: bool
    token_count: int
    content: str
    updated_at: str | None = None


class ChunkPage(BaseModel):
    total: int
    page: int
    size: int
    items: list[ChunkOut]


# ---------------- 检索调试 ----------------
class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = 10
    document_id: int | None = None


class RetrievalHitOut(BaseModel):
    chunk_id: int
    document_id: int
    filename: str
    page: int
    content: str
    vector_score: float
    bm25_score: float
    fused_score: float
    source: str


# ---------------- Agent ----------------
class ChatRequest(BaseModel):
    thread_id: str | None = None
    query: str = Field(..., min_length=1)


class ThreadOut(BaseModel):
    thread_id: str
    last_question: str | None = None
    updated_at: str | None = None


# ---------------- 偏好 ----------------
class PreferenceUpsert(BaseModel):
    key: str
    value: str
    description: str = ""


class PreferenceOut(BaseModel):
    key: str
    value: str
    description: str
    updated_at: str | None = None


# ---------------- 总览 ----------------
class ServiceHealth(BaseModel):
    postgres: str
    redis: str
    milvus: str
    db_backend: str


class OverviewOut(BaseModel):
    documents: int
    chunks: int
    agent_sessions: int
    services: ServiceHealth
    mock_mode: bool
