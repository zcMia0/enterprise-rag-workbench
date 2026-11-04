"""FastAPI 应用入口。

职责:
- 配置结构化日志与 CORS
- 挂载六大业务路由 (上传 / 文档 / Chunk / 检索 / Agent / 偏好) + 总览
- 启动时建表 (init_db)
- 生产形态下托管已构建的前端 dist (SPA 回退)
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import agent, chunks, documents, overview, preferences, retrieval, upload
from app.db.postgres import init_db
from app.logging_config import configure_logging, get_logger

configure_logging()
log = get_logger("main", "BOOT")

DIST_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("enterprise-rag-workbench backend starting ...")
    init_db()
    log.info("database tables ensured")
    yield
    log.info("backend shutdown")


app = FastAPI(
    title="Enterprise RAG Workbench",
    description="企业知识库 RAG Agent 工作台 (四层知识管理 + 混合检索 + Agent 对话)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (overview, upload, documents, chunks, retrieval, agent, preferences):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "enterprise-rag-workbench"}


# ---------------- 前端静态托管 (生产形态) ----------------
if os.path.isdir(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        # API 与静态资源之外一律回退到 index.html
        if full_path.startswith("api/") or full_path.startswith("docs"):
            return None  # type: ignore[return-value]
        index = os.path.join(DIST_DIR, "index.html")
        return FileResponse(index)


if __name__ == "__main__":
    import uvicorn

    from app.config import get_settings

    s = get_settings()
    uvicorn.run("app.main:app", host=s.backend_host, port=s.backend_port, reload=False)
