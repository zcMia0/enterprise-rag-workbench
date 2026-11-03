"""Agent 工具: 知识库检索工具 (供 LangGraph 工具调用节点使用)。

工具即"检索证据"。Agent 在生成前必须先调用此工具 (Prefetch 预检索),
工具返回结构化证据片段, 后续生成节点强制基于这些证据作答。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.retrieval.hybrid import get_retrieval_service

log = get_logger("agent", "TOOL")


@dataclass
class ToolResult:
    ok: bool
    evidence: list  # list[RetrievalHit]
    message: str = ""


def retrieval_tool(db: Session, query: str, top_k: int = 8) -> ToolResult:
    """检索知识库, 返回 Top-K 证据片段。

    这是 Agent 唯一允许的信息来源。若返回为空, 生成节点必须拒答 (防编造)。
    """
    log.info(f"[TOOL] knowledge retrieval invoked: {query[:40]!r}")
    svc = get_retrieval_service()
    hits = svc.retrieve(db, query, top_k=top_k)
    return ToolResult(ok=len(hits) > 0, evidence=hits, message=f"命中 {len(hits)} 条证据")
