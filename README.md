# 企业知识库 RAG Agent 工作台 (Enterprise RAG Workbench)

> 一套本地可运行的全栈企业知识库 RAG 系统：四层知识管理 + 双链路解析 + 混合检索 + Agent 对话溯源。
> **未配置任何密钥也能以 Mock 模式完整启动**（确定性哈希向量 + 规则化生成）

---

## 一、功能特性

| 能力 | 说明 |
|------|------|
| **分层知识管理** | Document → Section → Chunk → Vector 四层解耦，主数据 / 切分块 / 向量副本均可维护、可编辑、可重建 |
| **双链路文档处理** | 原生解析（PDF/Docx/Markdown/TXT）+ OCR 智能识别，按表格数 / 图片数 / 文本密度启发式路由 |
| **半结构化保护式切分** | 对 `<table>` / `<img>` 等块做保护，降低表格碎片化与结构丢失 |
| **混合检索** | Milvus 向量检索 + 应用层 BM25 + RRF 融合排序，提升标题词 / 字段名 / 表格字段命中率 |
| **Prefetch 预检索** | 模型生成前先完成证据检索并注入上下文，防止 Agent 绕开知识库 |
| **Agent 对话** | LangGraph 风格编排 + 工具调用 + 会话线程 + SSE 流式 + 来源溯源 |
| **运维能力** | Chunk 编辑 / 删除、文档级物理删除、索引重建、问答日志落库 |
| **RAG 整体面板** | 左侧六项导航 + 顶部总览看板（文档数 / 切分总量 / 会话数 / 服务状态实时） |

---

## 二、架构图

```
┌─────────────────────────── 前端 Vue3 + TS (Vite :5173) ───────────────────────────┐
│  总览看板 │ 上传入库 │ 文档管理 │ Chunk管理 │ 检索调试 │ Agent对话 │ 偏好管理          │
└───────────────┬───────────────────────────────────────────────────┬───────────────┘
                │  REST / SSE                                        │
┌───────────────▼───────────────────────────────────────────────────▼───────────────┐
│                      后端 FastAPI (:8000)                                       │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────────────────────┐   │
│  │ 解析路由    │ │ 保护式切分  │ │ 混合检索    │ │ Agent (LangGraph 风格编排)    │   │
│  │ native/ocr │ │ protected  │ │ vec+BM25+  │ │ 工具调用 / 线程 / 证据裁判 /   │   │
│  │ +启发式    │ │ split      │ │ RRF/Prefetch│ │ SSE 流式 / 来源溯源           │   │
│  └────────────┘ └────────────┘ └─────┬──────┘ └──────────────────────────────┘   │
└───────────────────────────────────────┼──────────────────────────────────────────┘
                                        │
        ┌───────────────┬───────────────┼───────────────┬───────────────┐
        ▼               ▼               ▼               ▼               ▼
   ┌─────────┐    ┌────────────┐   ┌──────────┐    ┌────────┐    ┌────────┐
   │ Milvus  │    │ PostgreSQL │   │  Redis   │    │ MySQL  │    │ Neo4j  │
   │(向量)    │    │ (主数据)   │   │(会话/缓存)│    │(可选)  │    │(图谱)  │
   └─────────┘    └────────────┘   └──────────┘    └────────┘    └────────┘
        （Mock 模式下以上分别降级为：本地向量文件 / SQLite / 内存字典）
```

---

## 三、技术栈

**后端**：Python · FastAPI · SQLAlchemy · LangChain/LangGraph(可选) · Milvus · PostgreSQL · Redis · OCR(RapidOCR/Paddle, 可选)
**前端**：Vue3 · TypeScript · Vite · Vue Router · Pinia · Axios(SSE)

---

## 四、快速开始

### 方式 A：零依赖 Mock 模式（推荐先体验，无需 Docker）

```bash
# 1) 启动依赖服务 (PostgreSQL / Redis / Milvus ...)，需 Docker Desktop
docker compose up -d

# 2) 后端 (自动走 Mock：SQLite + 本地向量 + 哈希嵌入 + 规则生成)
cd backend
python -m venv venv && venv/Scripts/activate        # Windows
pip install -r requirements.txt
cp .env.example .env                                # 可留空, 即 Mock 模式
python -m uvicorn app.main:app --reload --port 8000

# 3) 前端
cd ../frontend
npm install
npm run dev                                         # http://localhost:5173
```

> 不启动 Docker 也能跑：未配置 `DASHSCOPE_API_KEY` / `LLM_API_KEY` 时后端自动进入 Mock 模式，
> 使用 SQLite（替代 PG）、本地向量文件（替代 Milvus）、内存字典（替代 Redis），功能链路完整可用。

### 方式 B：真实服务 + 密钥

在 `.env` 中填入：

```ini
DASHSCOPE_API_KEY=sk-xxxx        # 通义千问嵌入 + 大模型
LLM_API_KEY=sk-xxxx
LLM_PROVIDER=dashscope
EMBEDDING_MODEL=text-embedding-v3
```

并安装可选依赖启用真实连接：`pip install -r requirements-optional.txt`（含 psycopg / pymilvus / openai / langgraph / pypdf / python-docx / rapidocr）。

---

## 五、API 示例

```bash
# 上传文档 (双链路解析 + 切分 + 向量化 + 索引)
curl -F "file=@sample.pdf" http://localhost:8000/api/upload

# 总览看板
curl http://localhost:8000/api/overview

# 检索调试 (返回向量分 / BM25 分 / 融合分)
curl -X POST http://localhost:8000/api/retrieval/debug \
  -H "Content-Type: application/json" \
  -d '{"query":"employee_id 是什么类型","top_k":5}'

# Agent 流式对话 (SSE)
curl -N -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"employee_id 字段的含义是什么"}'

# Chunk 编辑 / 删除 / 文档删除 / 索引重建
PUT    /api/chunks/{id}            {"content":"..."}
DELETE /api/chunks/{id}
DELETE /api/documents/{id}
POST   /api/documents/{id}/rebuild
```

完整路由见 `backend/app/api/*`。Swagger 文档：`http://localhost:8000/docs`。

---

## 六、目录结构

```
enterprise-rag-workbench/
├── docker-compose.yml          # Milvus(+etcd+minio) / PG / Redis / MySQL / Neo4j
├── .env.example                # 环境变量样例 (密钥永不入库)
├── .gitignore
├── LICENSE
├── backend/
│   ├── app/
│   │   ├── config.py           # 配置 + Mock 降级开关
│   │   ├── logging_config.py   # 结构化日志 ([模块] [阶段] 消息)
│   │   ├── db/                 # PG / Redis / SQLite 降级 + 四层模型
│   │   ├── parsers/            # 原生 + OCR + 启发式路由
│   │   ├── chunking/           # 保护式切分
│   │   ├── vector/             # 嵌入 + Milvus/本地向量
│   │   ├── retrieval/          # BM25 + RRF + 混合 + Prefetch
│   │   ├── agent/              # LLM + 工具 + LangGraph 风格编排 + SSE
│   │   ├── services/           # 文档 / Chunk / 偏好 / 统计
│   │   └── api/                # 七大路由
│   ├── tests/test_pipeline.py  # 管道冒烟测试
│   ├── requirements.txt        # 基础依赖 (Mock 可跑)
│   └── requirements-optional.txt
├── frontend/
│   └── src/{views,api,router,store}  # 7 个页面 + 统一请求(SSE)
└── scripts/                    # 示例文档 / 启动脚本
```

---

## 七、工程质量

- 后端：类型注解 + 函数 docstring + 结构化日志（`[RETRIEVER] hybrid retrieval started`）+ 统一错误处理。
- 关键链路日志清晰：检索 / 证据裁判 / 缓存命中 / 安全拦截 / 切分。
- 前端：组件化 + TypeScript + 请求封装统一处理 SSE 流。
- 密钥绝不入库：`.env` 已被 `.gitignore` 忽略。

---

## 八、License

[MIT](./LICENSE)
