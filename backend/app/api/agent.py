"""Agent 对话路由: SSE 流式 + 会话线程管理。

SSE 事件类型:
  token   : 逐片文本
  sources : 来源溯源 (chunk 级, 含各分数)
  done    : 结束 (含 used_knowledge 标记)
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agent.graph import AgentService
from app.db.models import QALog
from app.db.postgres import get_db
from app.schemas.rag import ChatRequest, ThreadOut

router = APIRouter(prefix="/api/agent", tags=["agent"])
_agent = AgentService()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(body: ChatRequest, db: Session = Depends(get_db)):
    """多轮对话 (SSE 流式)。无 thread_id 时自动新建会话。"""
    thread_id = body.thread_id or _agent.new_thread()

    def event_stream():
        yield _sse({"type": "meta", "data": {"thread_id": thread_id}})
        try:
            for event in _agent.run(db, thread_id, body.query):
                yield _sse(event)
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "data": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/threads", response_model=list[ThreadOut])
def list_threads(db: Session = Depends(get_db)):
    """会话列表: 每个 thread 的最近问题与消息数。"""
    rows = (
        db.query(
            QALog.thread_id,
            func.count(QALog.id).label("cnt"),
            func.max(QALog.created_at).label("last_at"),
        )
        .group_by(QALog.thread_id)
        .order_by(func.max(QALog.created_at).desc())
        .all()
    )
    out = []
    for tid, cnt, last_at in rows:
        first = (
            db.query(QALog.question)
            .filter(QALog.thread_id == tid)
            .order_by(QALog.id.asc())
            .first()
        )
        out.append(
            ThreadOut(
                thread_id=tid,
                last_question=first[0][:60] if first else None,
                updated_at=last_at.isoformat() if last_at else None,
            )
        )
    return out


@router.post("/threads", response_model=ThreadOut)
def new_thread():
    tid = _agent.new_thread()
    return ThreadOut(thread_id=tid)
