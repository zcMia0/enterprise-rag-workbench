"""本地管道冒烟测试: 直接调用服务层, 验证四层入库 + 检索 + Agent。

运行: cd backend && ./venv/Scripts/python.exe -m pytest tests/ -q  或
      cd backend && ./venv/Scripts/python.exe tests/test_pipeline.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.postgres import SessionLocal, init_db  # noqa: E402
from app.services.document_service import process_upload, rebuild_index  # noqa: E402
from app.services.chunk_service import list_chunks, update_chunk  # noqa: E402
from app.retrieval.hybrid import get_retrieval_service  # noqa: E402
from app.agent.graph import AgentService  # noqa: E402


def main() -> None:
    print("[test] start", flush=True)
    init_db()
    print("[test] db initialized", flush=True)
    db = SessionLocal()
    print("[test] session ok", flush=True)
    sample = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "scripts", "sample_doc.md"
    )
    with open(sample, "rb") as f:
        content = f.read()

    print("=== 1) 上传入库 ===")
    res = process_upload(db, "sample_doc.md", content)
    print(res)

    print("\n=== 2) Chunk 列表 (前 6) ===")
    pg = list_chunks(db, None, 1, 6)
    for c in pg["items"]:
        flag = "PROTECTED" if c["protected"] else "text"
        tag = "TABLE" if c["has_table"] else ("IMG" if c["has_image"] else "")
        print(f"  #{c['chunk_index']:>2} [{flag}/{tag}] {c['content'][:50].replace(chr(10),' ')}")

    print("\n=== 3) 检索调试 (employee_id) ===")
    svc = get_retrieval_service()
    hits = svc.retrieve(db, "employee_id 是什么类型", top_k=3)
    for h in hits:
        print(f"  cid={h.chunk_id} vec={h.vector_score} bm25={h.bm25_score} fused={h.fused_score} {h.filename}")

    print("\n=== 4) Agent 对话 (SSE 事件) ===")
    agent = AgentService()
    thread = agent.new_thread()
    for evt in agent.run(db, thread, "employee_id 字段的含义是什么"):
        if evt["type"] == "token":
            print(evt["data"], end="")
        elif evt["type"] == "sources":
            print(f"\n  [sources] {len(evt['data'])} 条")
        elif evt["type"] == "done":
            print(f"\n  [done] used_knowledge={evt['data']['used_knowledge']}")
    print()

    print("\n=== 5) Chunk 编辑后重建该文档索引 ===")
    first = pg["items"][0]["chunk_id"]
    upd = update_chunk(db, first, "[已编辑] " + pg["items"][0]["content"][:30])
    print("  edited chunk:", upd["chunk_id"], "len", len(upd["content"]))
    n = rebuild_index(db)
    print("  rebuild indexed:", n)
    db.close()
    print("\nALL_OK")


if __name__ == "__main__":
    main()
