"""Agent 对话编排: 工具调用 + 会话线程 + 证据裁判 + 流式生成 (SSE)。

流程 (与 LangGraph 状态机等价, 可选接入 langgraph):
    [RETRIEVE] 预检索证据 (Prefetch, 强制先查知识库)
        │
    [ADJUDICATE] 证据裁判: 证据是否充分? 不充分则标记 used_knowledge=False (防编造)
        │
    [GENERATE] 基于证据流式生成, 逐 token 推送给前端

会话线程: thread_id 维护多轮历史 (Redis 或内存), 支持来源延续。
来源溯源: 生成结束后随 SSE 'sources' 事件回传 chunk 级证据。
"""
from __future__ import annotations

from typing import Generator

from sqlalchemy.orm import Session

from app.agent.llm import LLMService
from app.agent.tools import retrieval_tool
from app.config import get_settings
from app.db.redis_client import redis_client
from app.logging_config import get_logger

log = get_logger("agent", "GRAPH")

_settings = get_settings()

# 尝试启用 LangGraph (可选, 不影响功能)
try:
    from langgraph.graph import END, StateGraph  # type: ignore

    HAS_LANGGRAPH = True
except Exception:  # noqa: BLE001
    HAS_LANGGRAPH = False


class AgentService:
    def __init__(self) -> None:
        self.llm = LLMService()
        self.system_prompt = (
            "你是企业知识库助手。必须严格基于提供的知识库证据作答, "
            "不得编造知识库之外的信息。若证据不足, 明确说明无法回答。"
        )

    # ---------------- 会话线程 (内存/Redis) ----------------
    def _thread_key(self, thread_id: str) -> str:
        return f"rag:thread:{thread_id}"

    def load_history(self, thread_id: str, limit: int = 10) -> list[dict]:
        raw = redis_client.get(self._thread_key(thread_id))
        if not raw:
            return []
        try:
            import json

            hist = json.loads(raw) if isinstance(raw, str) else raw
            return hist[-limit:]
        except Exception:  # noqa: BLE001
            return []

    def save_turn(self, thread_id: str, role: str, content: str) -> None:
        hist = self.load_history(thread_id, limit=50)
        hist.append({"role": role, "content": content})
        try:
            import json

            redis_client.set(self._thread_key(thread_id), json.dumps(hist, ensure_ascii=False), ex=60 * 60 * 24 * 7)
        except Exception:  # noqa: BLE001
            pass

    def new_thread(self) -> str:
        import uuid

        return uuid.uuid4().hex

    # ---------------- 偏好注入 ----------------
    def load_preferences(self, db: Session) -> str:
        from app.db.models import Preference

        prefs = db.query(Preference).all()
        if not prefs:
            return ""
        return "\n".join(f"- {p.key}: {p.value}" for p in prefs)

    # ---------------- 主运行 (生成器, 产出 SSE 事件) ----------------
    def run(self, db: Session, thread_id: str, query: str) -> Generator[dict, None, None]:
        """执行一轮对话, 逐事件产出供 SSE 推送。

        Yields dicts: {type:'token',data} | {type:'sources',data} | {type:'done',data}
        """
        log.info(f"[RETRIEVE] prefetch evidence for thread={thread_id[:8]} query={query[:40]!r}")
        tool_res = retrieval_tool(db, query, top_k=8)
        evidence = tool_res.evidence

        # [ADJUDICATE] 证据裁判
        used_knowledge = len(evidence) > 0
        log.info(
            f"[EVIDENCE] adjudication -> used_knowledge={used_knowledge}, "
            f"hits={len(evidence)}"
        )

        # 组装 prompt
        history = self.load_history(thread_id)
        pref_text = self.load_preferences(db)
        sys_prompt = self.system_prompt
        if pref_text:
            sys_prompt += f"\n\n用户偏好/记忆:\n{pref_text}"

        evidence_text = "\n---\n".join(
            f"[{h.filename} p{h.page}] (vec={h.vector_score}, bm25={h.bm25_score}, "
            f"fused={h.fused_score})\n{h.content[:300]}"
            for h in evidence
        ) or "（无）"

        full_prompt = (
            f"<<QUESTION>>\n{query}\n<<EVIDENCE>>\n{evidence_text}\n<<END>>"
        )

        # 流式生成
        collected: list[str] = []
        log.info("[GENERATE] streaming answer start")
        for tok in self.llm.generate_stream(sys_prompt, full_prompt):
            collected.append(tok)
            yield {"type": "token", "data": tok}

        answer = "".join(collected)

        # 来源溯源事件
        sources = [
            {
                "chunk_id": h.chunk_id,
                "filename": h.filename,
                "page": h.page,
                "vector_score": h.vector_score,
                "bm25_score": h.bm25_score,
                "fused_score": h.fused_score,
                "content": h.content[:200],
            }
            for h in evidence
        ]
        yield {"type": "sources", "data": sources}

        # 落库
        self._persist_qa(db, thread_id, query, answer, sources, used_knowledge)

        # 历史
        self.save_turn(thread_id, "user", query)
        self.save_turn(thread_id, "assistant", answer)

        yield {"type": "done", "data": {"used_knowledge": used_knowledge}}

    def _persist_qa(self, db, thread_id, question, answer, sources, used_knowledge) -> None:  # noqa: ANN001
        from app.db.models import QALog

        try:
            rec = QALog(
                thread_id=thread_id,
                question=question,
                answer=answer,
                sources=sources,
                used_knowledge=used_knowledge,
            )
            db.add(rec)
            db.commit()
            log.info(f"[LOG] qa logged thread={thread_id[:8]} used_kb={used_knowledge}")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning(f"[LOG] qa persist failed: {exc}")


# LangGraph 适配器 (可选): 把上述节点编译成图, 与状态机等价
def build_langgraph():
    if not HAS_LANGGRAPH:
        return None

    class AgentState(dict):  # noqa: D101
        pass

    # 轻量示例: 仅演示图结构 (检索 -> 裁判 -> 结束), 生成在图外流式进行
    def retrieve(state):  # noqa: ANN001
        return state

    def adjudicate(state):  # noqa: ANN001
        return state

    g = StateGraph(AgentState)
    g.add_node("retrieve", retrieve)
    g.add_node("adjudicate", adjudicate)
    g.add_edge("retrieve", "adjudicate")
    g.add_edge("adjudicate", END)
    return g.compile()
