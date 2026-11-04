"""应用配置 (环境变量 + .env + Mock 降级开关)。

设计要点:
- 所有外部依赖(DashScope / Milvus / PG / Redis)均通过环境变量注入, 绝不硬编码密钥。
- 当关键密钥缺失或 FORCE_MOCK=true 时, 自动进入 Mock 降级模式, 保证项目离线可启动。
- 该模块是全局唯一读取配置的来源, 其它模块通过 get_settings() 单例获取。
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- 基础 ----
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    log_level: str = "INFO"
    force_mock: bool = False

    # ---- PostgreSQL ----
    database_url: str = "postgresql+psycopg://rag:rag123456@localhost:5432/rag_workbench"
    # 本地无 PG 时的开发兜底库 (SQLite), 仅用于离线演示
    sqlite_fallback: str = "sqlite:///./data/rag_dev.db"

    # ---- Redis ----
    redis_url: str = "redis://localhost:6379/0"

    # ---- Milvus ----
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "rag_chunks"

    # ---- 嵌入模型 ----
    dashscope_api_key: str = ""
    embedding_model: str = "text-embedding-v3"
    embedding_dim: int = 1024

    # ---- 大模型 ----
    llm_provider: Literal["dashscope", "openai", "mock"] = "mock"
    llm_api_key: str = ""
    llm_model: str = "qwen-max"
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ---- OCR ----
    ocr_engine: Literal["paddle", "rapid", "mock"] = "mock"

    # ---- 检索 / 切分参数 ----
    chunk_size: int = 600
    chunk_overlap: int = 80
    bm25_top_k: int = 20
    vector_top_k: int = 10
    # RRF 常数: 与候选列表长度同量级。60 是面向万级语料的通用值,
    # 企业库单查询候选仅几十条时取 10 更合适(见 eval/report.md 的参数扫描)。
    rrf_k: int = 10
    # 两路融合权重: 词面(BM25) 置 1.0, 向量略降权。
    # 依据: 弱嵌入下向量路会稀释强词面路; 接入真实嵌入模型后可将向量权重调回 1.0。
    rrf_weight_vector: float = 0.4
    rrf_weight_bm25: float = 1.0
    hybrid_fetch_k: int = 30
    # ---- 证据裁判 (防编造闸门) ----
    # 判定"证据是否可用"的口径: 问题里的内容词, 在召回的前 N 条证据里至少命中几个。
    # 取 2 的依据是 eval 实测(见 eval/report.md 第 3 节): 91 道范围内问题接受率 94.5%,
    # 10 道完全无关问题拒答 10/10。降到 1 会把无关问题也放行, 升到 3 会误拒正常问题。
    evidence_min_terms: int = 2
    evidence_gate_top_n: int = 3

    # ---- 运行时派生: 是否处于 Mock 模式 ----
    @property
    def mock_mode(self) -> bool:
        """综合判断: 强制 Mock, 或关键密钥缺失 -> Mock 模式。

        只要 DashScope 嵌入密钥 或 大模型密钥 任一缺失, 即整体进入 Mock 降级,
        保证未配置任何密钥时项目也能完整启动 (确定性哈希嵌入 + 规则化生成)。
        """
        if self.force_mock:
            return True
        if not self.dashscope_api_key or not self.llm_api_key:
            return True
        return False

    @property
    def use_sqlite(self) -> bool:
        """未配置真实 PG 且非显式 PG 时, 本地用 SQLite 兜底。"""
        if self.force_mock:
            return True
        # 仅当 URL 仍是默认 localhost PG 且无可达服务时, 由启动逻辑决定;
        # 这里保守: 默认 PG, 启动若连接失败再回退(见 db/postgres.py)。
        return False


@lru_cache
def get_settings() -> Settings:
    """全局配置单例。"""
    return Settings()


def resolve_db_url(settings: Settings | None = None) -> str:
    """解析最终使用的数据库 URL。

    优先级: 显式 PG(默认) -> SQLite 兜底。
    Mock 模式或显式 force 时使用 SQLite, 便于无 Docker 环境直接运行。
    """
    s = settings or get_settings()
    if s.mock_mode or s.use_sqlite:
        return s.sqlite_fallback
    return s.database_url
