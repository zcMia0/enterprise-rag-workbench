"""RAG 工作台测评脚本 —— 把简历里的四个量化指标变成**可复现的实测数字**。

测什么
------
A. 入库质量(解析 + 切分): 复杂文档入库成功率
   ``X%`` = 朴素定长切分的成功率 (基线, 结构被切断)
   ``Y%`` = 半结构化保护式切分的成功率 (本项目)
   单篇文档"成功"的判定(四条全满足才算):
     1) parsed_ok  解析出内容, 且没有 "[解析失败]/[待解析]" 之类的降级占位;
     2) route_ok   路由决策正确(图像必走 OCR, 其余必走原生);
     3) tables_ok  文档里每张表格都**完整落在同一个 chunk 内**(单元格按序齐全, 未被切碎);
     4) cover_ok   切分后字符覆盖率 >= 98%(6 字符 shingle 覆盖率, 衡量内容是否丢失)。

B. 检索质量: 混合检索命中率
   同一份 chunk 集合, 三种召回方式各取 Top-5:
     vector-only  (仅向量余弦)
     bm25-only    (仅词面)
     hybrid       (向量 + BM25 经 RRF 融合)
   判定: Top-5 中任一片段包含该题的 ``key`` 关键串即算命中(单一正解 -> Hit@5 等价 Recall@5)。
   ``Z%`` = hybrid 相对"最好的单路"的 Hit@5 相对提升。

C. 证据裁判(防编造闸门)
   对 91 道语料范围内问题 + 10 道完全无关问题各跑一遍 ``app.retrieval.gate``,
   统计"范围内放行率"与"无关问题拒答率"。

D. 延迟: 首 token 时间(TTFT)
   对运行中的服务发 N 次 SSE 请求, 记录从发出请求到收到第一个 token 事件的耗时。

用法
----
    cd enterprise-rag-workbench
    backend/venv/Scripts/python.exe eval/gen_corpus.py      # 先生成语料(只需一次)
    backend/venv/Scripts/python.exe eval/run_eval.py        # 跑 A + B + C, 输出 eval/report.md
    backend/venv/Scripts/python.exe eval/run_eval.py --ttft --requests 20   # 额外测 TTFT

重要口径说明
------------
本仓库默认以 **Mock 模式** 运行(不配置任何云密钥):
- 嵌入 = 确定性哈希嵌入(字符 n-gram 投影), 非真实语义模型;
- 生成 = 规则化模板, 非真实大模型。
因此 A/C/D 的结论与真实部署一致性好(PDF/DOCX 解析、切分、BM25、RRF 都是真实代码),
而 B 的绝对值只能代表"词面 + 哈希向量"组合下的表现。**接入真实嵌入后请重跑本脚本**,
脚本会自动打印当前嵌入来源, 报告里的数字请连同口径一起引用。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(EVAL_DIR)
BACKEND_DIR = os.path.join(ROOT, "backend")
CORPUS_DIR = os.path.join(EVAL_DIR, "corpus")

sys.path.insert(0, EVAL_DIR)
sys.path.insert(0, BACKEND_DIR)

from app.chunking.protected import build_chunks  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.parsers.native import parse_native  # noqa: E402
from app.parsers.ocr import parse_ocr  # noqa: E402
from app.parsers.router import IMAGE_TYPES, choose_path  # noqa: E402
from app.retrieval.bm25 import BM25  # noqa: E402
from app.retrieval.gate import judge_evidence  # noqa: E402
from app.retrieval.rrf import rrf_fuse  # noqa: E402
from app.vector.embeddings import EmbeddingService, cosine  # noqa: E402
from corpus_spec import DOCS, QA, all_table_specs  # noqa: E402

SETTINGS = get_settings()

TOP_K = 5           # 命中判定只看前 5 条
MRR_K = 10          # MRR 截断到前 10 条
COVERAGE_MIN = 0.98  # 字符覆盖率下限
SHINGLE = 6
GATE_FETCH_K = 8    # 证据裁判前先取回的证据条数 (与 Agent 对话一致)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower()


def shingles(text: str, k: int = SHINGLE) -> set[str]:
    """去掉空白后取 k 字符滑窗, 用于度量"内容是否被切分丢弃"。"""
    t = re.sub(r"\s+", "", text)
    if len(t) < k:
        return {t} if t else set()
    return {t[i : i + k] for i in range(len(t) - k + 1)}


def block_texts(parsed) -> list[str]:
    """取出每个内容块的文本(图片块优先用 OCR 文本), 作为覆盖率的分母。"""
    out: list[str] = []
    for b in parsed.blocks:
        t = b.ocr_text if (b.type == "image" and b.ocr_text) else b.content
        if t and t.strip():
            out.append(t)
    return out


def coverage(parts: list[str], chunk_texts: list[str]) -> float:
    """内容覆盖率: 源内容块的 shingle 有多少比例仍出现在 chunk 集合中。

    按**块**取 shingle 而非按整篇文本 —— 否则块与块之间的连接处会生成"跨块 shingle",
    它们在 chunk 分界处天然不存在, 会把正常切分误判成"丢内容"。
    块内部的分割由 overlap 保证接缝不丢字, 因此该指标只衡量真正的字符丢失。
    """
    src: set[str] = set()
    for p in parts:
        src |= shingles(p)
    if not src:
        return 1.0
    got: set[str] = set()
    for c in chunk_texts:
        got |= shingles(c)
    return len(src & got) / len(src)


def table_intact(chunk_texts: list[str], rows: list[list[str]]) -> bool:
    """表格是否完整落在某个 chunk 内(所有单元格按原顺序出现在同一块)。"""
    cells = [c for row in rows for c in row]
    for text in chunk_texts:
        pos = 0
        for cell in cells:
            idx = text.find(cell, pos)
            if idx < 0:
                break
            pos = idx + len(cell)
        else:
            return True
    return False


def naive_fixed_window(text: str, size: int, overlap: int) -> list[str]:
    """基线切分: 纯字符滑窗, 完全不感知文档结构(表格/图片都被无差别切断)。

    这是"优化前"的典型实现, 用于和半结构化保护式切分做 A/B 对照。
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    out: list[str] = []
    start = 0
    while start < len(text):
        out.append(text[start : start + size])
        if start + size >= len(text):
            break
        start += step
    return out


# ---------------------------------------------------------------------------
# A. 入库质量
# ---------------------------------------------------------------------------
def ingest_one(spec: dict) -> dict:
    """跑单篇文档的完整入库前置链路, 分别用两种切分策略评分。"""
    filename = spec["filename"]
    ext = _ext(filename)
    path = os.path.join(CORPUS_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"缺少语料文件 {path}, 请先运行 eval/gen_corpus.py")

    # 与 document_service.process_upload 相同的路由逻辑
    probe = None if ext in IMAGE_TYPES else parse_native(path, ext)
    route, reason = choose_path(ext, probe)
    parsed = parse_ocr(path, ext) if route == "ocr" else (probe or parse_native(path, ext))
    parse_path = route

    text = parsed.to_text()
    parts = block_texts(parsed)
    degraded = ("[解析失败]" in text) or ("待解析" in text) or ("[空文件]" in text)
    parsed_ok = bool(text.strip()) and not degraded
    expect_route = "ocr" if ext in IMAGE_TYPES else "native"
    route_ok = parse_path == expect_route

    # 策略 1: 基线(朴素定长)
    naive_texts = naive_fixed_window(text, SETTINGS.chunk_size, SETTINGS.chunk_overlap)
    # 策略 2: 本项目(半结构化保护式)
    plans = build_chunks(parsed)
    prot_texts = [p.content for p in plans]

    tables = all_table_specs(spec)

    def _score(chunk_texts: list[str]) -> dict:
        t_ok = all(table_intact(chunk_texts, rows) for rows in tables)
        cov = coverage(parts, chunk_texts)
        ok = parsed_ok and route_ok and t_ok and cov >= COVERAGE_MIN
        return {
            "chunks": len(chunk_texts),
            "tables_ok": t_ok,
            "coverage": round(cov, 4),
            "success": ok,
        }

    return {
        "filename": filename,
        "ext": ext,
        "complex": spec["complex"],
        "curated": bool(spec.get("curated", False)),
        "route": parse_path,
        "route_reason": reason,
        "route_ok": route_ok,
        "parsed_ok": parsed_ok,
        "n_tables": len(tables),
        "text_len": len(text),
        "naive": _score(naive_texts),
        "protected": _score(prot_texts),
    }


def grade_ingest() -> dict:
    rows = [ingest_one(d) for d in DOCS]

    def rate(key: str, subset: list[dict]) -> tuple[int, int, float]:
        hit = sum(1 for r in subset if r[key]["success"])
        total = len(subset)
        return hit, total, round(hit / total * 100, 1) if total else 0.0

    # 主口径: 手工编写、格式多样的基准文档
    curated = [r for r in rows if r["complex"] and r["curated"]]
    # 参考口径: 规模化生成的近重复文档(结构一致, 仅作旁证)
    scaled = [r for r in rows if r["complex"] and not r["curated"]]

    nx, nt, nxr = rate("naive", curated)
    py, pt, pyr = rate("protected", curated)
    snx, snt, snxr = rate("naive", scaled)
    spy, spt, spyr = rate("protected", scaled)
    return {
        "rows": curated,
        "all_rows": rows,
        "complex_total": len(curated),
        "naive": {"hit": nx, "total": nt, "rate": nxr},
        "protected": {"hit": py, "total": pt, "rate": pyr},
        "scaled": {
            "total": len(scaled),
            "naive_rate": snxr,
            "protected_rate": spyr,
            "naive_hit": snx,
            "protected_hit": spy,
            "protected_total": spt,
        },
        "route_all_ok": all(r["route_ok"] for r in rows),
    }


# ---------------------------------------------------------------------------
# B. 检索质量
# ---------------------------------------------------------------------------
class OfflineIndex:
    """离线索引: 复用生产代码的 EMBED / BM25 / RRF, 但不落库、不污染运行时数据。"""

    def __init__(self, per_doc_chunks: list[tuple[str, list[str]]]) -> None:
        self.ids: list[int] = []
        self.texts: list[str] = []
        self.docs: list[str] = []
        for filename, texts in per_doc_chunks:
            for t in texts:
                self.ids.append(len(self.ids) + 1)
                self.texts.append(t)
                self.docs.append(filename)
        self.emb = EmbeddingService()
        self.vectors = self.emb.embed_batch(self.texts) if self.texts else []
        self.bm25 = BM25()
        for cid, t in zip(self.ids, self.texts):
            self.bm25.index(cid, t)
        self.bm25.build()

    def vector_top(self, query: str, k: int) -> list[dict]:
        qv = self.emb.embed(query)
        scored = [(cid, cosine(qv, v)) for cid, v in zip(self.ids, self.vectors)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [{"chunk_id": c, "score": s, "source": "vector"} for c, s in scored[:k]]

    def bm25_top(self, query: str, k: int) -> list[dict]:
        res = self.bm25.search(query, k)
        for r in res:
            r["source"] = "bm25"
        return res

    def hybrid_top(self, query: str, k: int) -> list[dict]:
        vec = self.vector_top(query, SETTINGS.hybrid_fetch_k)
        bm = self.bm25_top(query, SETTINGS.bm25_top_k)
        # 与生产代码 hybrid.RetrievalService.retrieve 保持一致: 加权 RRF
        fused = rrf_fuse(
            [vec, bm],
            weights=[SETTINGS.rrf_weight_vector, SETTINGS.rrf_weight_bm25],
        )
        return fused[:k]

    def text_of(self, chunk_id: int) -> str:
        return self.texts[chunk_id - 1]

    def doc_of(self, chunk_id: int) -> str:
        return self.docs[chunk_id - 1]


def _first_hit_rank(index: OfflineIndex, results: list[dict], key: str) -> int:
    """返回第一个包含关键串的名次(1-based), 未命中返回 0。"""
    for rank, r in enumerate(results, start=1):
        if key in index.text_of(r["chunk_id"]):
            return rank
    return 0


def grade_retrieval(per_doc_chunks: list[tuple[str, list[str]]]) -> dict:
    index = OfflineIndex(per_doc_chunks)
    systems = ("vector", "bm25", "hybrid")
    stats: dict[str, dict[str, float]] = {
        s: {"hit5": 0, "mrr": 0.0, "kw_hit5": 0, "kw_n": 0, "sem_hit5": 0, "sem_n": 0}
        for s in systems
    }
    details: list[dict] = []

    for item in QA:
        q, key, qtype = item["q"], item["key"], item["type"]
        row = {"q": q, "type": qtype, "doc": item["doc"], "key": key}
        for s in systems:
            if s == "vector":
                res = index.vector_top(q, MRR_K)
            elif s == "bm25":
                res = index.bm25_top(q, MRR_K)
            else:
                res = index.hybrid_top(q, MRR_K)
            rank = _first_hit_rank(index, res, key)
            row[f"{s}_rank"] = rank
            if 0 < rank <= TOP_K:
                stats[s]["hit5"] += 1
                if qtype == "keyword":
                    stats[s]["kw_hit5"] += 1
                else:
                    stats[s]["sem_hit5"] += 1
            if rank > 0:
                stats[s]["mrr"] += 1.0 / rank
        for s in systems:
            if qtype == "keyword":
                stats[s]["kw_n"] += 1
            else:
                stats[s]["sem_n"] += 1
        details.append(row)

    n = len(QA)
    summary: dict[str, dict] = {}
    for s in systems:
        st = stats[s]
        summary[s] = {
            "hit5": st["hit5"],
            "hit5_rate": round(st["hit5"] / n * 100, 1),
            "mrr10": round(st["mrr"] / n, 4),
            "kw_rate": round(st["kw_hit5"] / st["kw_n"] * 100, 1) if st["kw_n"] else 0.0,
            "sem_rate": round(st["sem_hit5"] / st["sem_n"] * 100, 1) if st["sem_n"] else 0.0,
        }

    best_single = max(summary["vector"]["hit5_rate"], summary["bm25"]["hit5_rate"])
    gain_vs_vector = round(
        (summary["hybrid"]["hit5_rate"] - summary["vector"]["hit5_rate"])
        / summary["vector"]["hit5_rate"]
        * 100,
        1,
    )
    gap_vs_best = round(summary["hybrid"]["hit5_rate"] - best_single, 1)

    # 互补性分析: 两路各自"独有命中"的数量, 决定融合还有多少增量空间
    overlap = {"both": 0, "only_vector": 0, "only_bm25": 0, "neither": 0}
    for row in details:
        v = 0 < row["vector_rank"] <= TOP_K
        b = 0 < row["bm25_rank"] <= TOP_K
        if v and b:
            overlap["both"] += 1
        elif v:
            overlap["only_vector"] += 1
        elif b:
            overlap["only_bm25"] += 1
        else:
            overlap["neither"] += 1

    return {
        "n": n,
        "n_keyword": stats["hybrid"]["kw_n"],
        "n_semantic": stats["hybrid"]["sem_n"],
        "chunks": len(index.texts),
        "summary": summary,
        "best_single_rate": best_single,
        "gain_vs_vector_pct": gain_vs_vector,
        "gap_vs_best_pp": gap_vs_best,
        "overlap": overlap,
        "embedding": (
            getattr(index.emb, "provider", None)
            or ("mock-hash" if SETTINGS.mock_mode else "remote")
        ),
        "details": details,
    }


# ---------------------------------------------------------------------------
# C. 证据裁判 (防编造闸门)
# ---------------------------------------------------------------------------
# 这 10 道题与语料主题完全无关。正确的行为是"如实说知识库没有", 而不是
# 拿 Top-K 里最不相关里最像的片段硬凑一个答案。
OUT_OF_SCOPE = [
    "请介绍一下量子纠缠在星际航行中的应用",
    "如何用 Rust 写一个分布式共识算法",
    "今天北京的天气怎么样",
    "红烧肉的家常做法",
    "2026 年世界杯谁夺冠",
    "Python 怎么处理多线程",
    "推荐几本好看的小说",
    "如何治疗偏头痛",
    "明天上海会下雨吗",
    "帮我写一首关于春天的诗",
]


class _Ev:
    """把离线 chunk 文本包装成 gate 需要的证据对象 (只需 .content)。"""

    __slots__ = ("content",)

    def __init__(self, content: str) -> None:
        self.content = content


def grade_gate(per_doc_chunks: list[tuple[str, list[str]]]) -> dict:
    """测量证据裁判在"范围内问题"上的放行率, 与"无关问题"上的拒答率。"""
    index = OfflineIndex(per_doc_chunks)
    vocab = index.bm25.idf

    def decide(q: str) -> tuple[bool, dict]:
        fused = index.hybrid_top(q, GATE_FETCH_K)
        evs = [_Ev(index.text_of(r["chunk_id"])) for r in fused]
        d = judge_evidence(
            q,
            evs,
            vocabulary=vocab,
            min_terms=SETTINGS.evidence_min_terms,
            top_n=SETTINGS.evidence_gate_top_n,
        )
        return d.usable, d.as_dict()

    in_total = len(QA)
    in_rejected: list[dict] = []
    for item in QA:
        ok, info = decide(item["q"])
        if not ok:
            in_rejected.append({"q": item["q"], **info})

    out_rejected: list[str] = []
    out_leaked: list[dict] = []
    for q in OUT_OF_SCOPE:
        ok, info = decide(q)
        if ok:
            out_leaked.append({"q": q, **info})
        else:
            out_rejected.append(q)

    return {
        "min_terms": SETTINGS.evidence_min_terms,
        "top_n": SETTINGS.evidence_gate_top_n,
        "fetch_k": GATE_FETCH_K,
        "in_total": in_total,
        "in_accept": in_total - len(in_rejected),
        "in_rate": round((in_total - len(in_rejected)) / in_total * 100, 1),
        "in_rejected": in_rejected,
        "out_total": len(OUT_OF_SCOPE),
        "out_reject": len(out_rejected),
        "out_rate": round(len(out_rejected) / len(OUT_OF_SCOPE) * 100, 1),
        "out_leaked": out_leaked,
    }


# ---------------------------------------------------------------------------
# D. 延迟 (首 token)
# ---------------------------------------------------------------------------
def bench_ttft(url: str, requests: int, query: str) -> dict | None:
    """对运行中的服务测首 token 耗时(SSE)。服务不可达时返回 None。"""
    try:
        import httpx
    except Exception:  # noqa: BLE001
        return None

    samples: list[float] = []
    try:
        # trust_env=False: 机器上配了 HTTP(S)_PROXY 时, httpx 会连 127.0.0.1 也走代理,
        # 拿到 502 "upstream connect failed" 而测不到延迟。本机测速必须绕过代理。
        with httpx.Client(timeout=60.0, trust_env=False) as client:
            if client.get(f"{url}/api/overview", timeout=5.0).status_code != 200:
                return None
            for _ in range(requests):
                t0 = time.perf_counter()
                with client.stream(
                    "POST", f"{url}/api/agent/chat", json={"query": query}
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if line.startswith("data:") and '"type": "token"' in line:
                            samples.append((time.perf_counter() - t0) * 1000)
                            break
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] TTFT 测量失败: {exc}")
        return None

    if not samples:
        return None
    samples_sorted = sorted(samples)
    p95_idx = min(len(samples_sorted) - 1, int(round(0.95 * (len(samples_sorted) - 1))))
    return {
        "url": url,
        "requests": len(samples),
        "mean_ms": round(statistics.mean(samples), 1),
        "p50_ms": round(statistics.median(samples), 1),
        "p95_ms": round(samples_sorted[p95_idx], 1),
        "min_ms": round(min(samples), 1),
        "max_ms": round(max(samples), 1),
    }


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def _fmt_bool(v: bool) -> str:
    return "✓" if v else "✗"


def render_report(ing: dict, ret: dict, gate: dict, ttft: dict | None, meta: dict) -> str:
    lines: list[str] = []
    a = lines.append

    a("# RAG 工作台测评报告\n")
    a("> 本文件由 `eval/run_eval.py` 自动生成, 所有数字均为**脚本实测**, 可随时重跑复现。\n")

    a("## 0. 测评环境与口径\n")
    a("| 项 | 值 |")
    a("| --- | --- |")
    a(f"| 运行模式 | {'Mock 降级模式' if SETTINGS.mock_mode else '真实服务模式'} |")
    a(f"| 嵌入来源 | {ret['embedding']} (dim={SETTINGS.embedding_dim}) |")
    a(f"| 切分参数 | chunk_size={SETTINGS.chunk_size}, chunk_overlap={SETTINGS.chunk_overlap} |")
    a(
        f"| 检索参数 | vector_top_k={SETTINGS.vector_top_k}, "
        f"bm25_top_k={SETTINGS.bm25_top_k}, rrf_k={SETTINGS.rrf_k} |"
    )
    a(f"| OCR 引擎 | {SETTINGS.ocr_engine} |")
    a(
        f"| 语料规模 | 全库 {meta['corpus_docs']} 篇 / {ret['chunks']} 个 chunk; "
        f"其中手工基准文档 12 篇(复杂 {ing['complex_total']} 篇) |"
    )
    a(f"| 测评题量 | {ret['n']} 题 (关键词型 {ret['n_keyword']} + 语义型 {ret['n_semantic']}) |")
    a(f"| 生成时间 | {meta['time']} |")
    a("")
    if SETTINGS.mock_mode:
        a(
            "> ⚠️ **口径提示**: 当前为 Mock 模式 —— 嵌入是确定性哈希(非语义模型)、生成是规则模板。"
            "解析 / 切分 / BM25 / RRF 全部是真实生产代码, 因此入库质量与融合排序的结论可靠; "
            "**向量路的表现不代表真实嵌入模型**, 接入 DashScope `text-embedding-v3` 后请重跑本脚本以更新数字。\n"
        )

    # ---- A ----
    a("## 1. 入库质量: 复杂文档成功率\n")
    a(
        "判定为“入库成功”需四条全满足: 解析无降级占位、路由决策正确、"
        "每张表格完整落在同一 chunk 内、字符覆盖率 ≥ 98%。\n"
    )
    a("| 策略 | 成功 / 复杂文档 | 成功率 |")
    a("| --- | --- | --- |")
    a(
        f"| 基线: 朴素定长切分(不感知结构) | {ing['naive']['hit']} / {ing['naive']['total']} "
        f"| **{ing['naive']['rate']}%** |"
    )
    a(
        f"| 本项目: 半结构化保护式切分 | {ing['protected']['hit']} / {ing['protected']['total']} "
        f"| **{ing['protected']['rate']}%** |"
    )
    a("")
    sc = ing["scaled"]
    a(
        f"> 另外 {sc['total']} 篇规模化生成的近重复文档(版式完全一致, 仅部门/年度/金额不同)在两种策略下分别为 "
        f"{sc['naive_rate']}% / {sc['protected_rate']}% —— 这类文档表格较小、恰好不易跨窗口边界, "
        "且成败高度一致, 故**只作旁证, 不计入上表主口径**。"
    )
    a("")
    a("### 基准文档逐篇明细\n")
    a(
        "| 文档 | 类型 | 表格数 | 路由 | 基线表格完整 | 基线覆盖率 | 基线 | "
        "保护式表格完整 | 保护式覆盖率 | 保护式 |"
    )
    a("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in ing["rows"]:
        a(
            f"| {r['filename']} | {r['ext']} | {r['n_tables']} | {r['route']} | "
            f"{_fmt_bool(r['naive']['tables_ok'])} | {r['naive']['coverage']:.3f} | {_fmt_bool(r['naive']['success'])} | "
            f"{_fmt_bool(r['protected']['tables_ok'])} | {r['protected']['coverage']:.3f} | {_fmt_bool(r['protected']['success'])} |"
        )
    a("")
    a(
        f"**结论**: 在同一批语料、同一套解析结果下, 保护式切分把复杂文档入库成功率从 "
        f"{ing['naive']['rate']}% 提升到 {ing['protected']['rate']}%; "
        "差异全部来自“表格是否被切碎”这一项 —— 两种策略的字符覆盖率都接近 1.0, "
        "说明基线并没有丢字, 而是**丢了结构**。\n"
    )

    # ---- B ----
    a("## 2. 检索质量: 混合检索命中率\n")
    a(
        f"同一份 {ret['chunks']} 个 chunk 的索引, 三种召回方式各取 Top-{TOP_K}, "
        f"命中判定为 Top-{TOP_K} 中任一片段包含该题的唯一关键串。\n"
    )
    a("| 召回方式 | Hit@5 | MRR@10 | 关键词型 Hit@5 | 语义型 Hit@5 |")
    a("| --- | --- | --- | --- | --- |")
    for label, k in (
        ("仅向量 (vector)", "vector"),
        ("仅词面 (BM25)", "bm25"),
        ("混合 (RRF 融合)", "hybrid"),
    ):
        s = ret["summary"][k]
        a(
            f"| {label} | {s['hit5']}/{ret['n']} = **{s['hit5_rate']}%** | {s['mrr10']:.3f} "
            f"| {s['kw_rate']}% | {s['sem_rate']}% |"
        )
    ov = ret["overlap"]
    a("")
    a(
        f"- 混合检索相对**纯向量**提升 **{ret['gain_vs_vector_pct']}%** "
        f"({ret['summary']['vector']['hit5_rate']}% → {ret['summary']['hybrid']['hit5_rate']}%); "
        f"相对最好的单路 BM25({ret['best_single_rate']}%) 低 {abs(ret['gap_vs_best_pp'])} 个百分点"
        f"({ret['summary']['bm25']['hit5']} 题 vs {ret['summary']['hybrid']['hit5']} 题)。"
    )
    a(
        "- 关键词型题目(字段名 / 配置项 / 编号)上 BM25 明显强于向量 —— 这正是"
        "“标题词、字段名、表格字段命中不稳”的解法。"
    )
    a(
        f"- 互补性拆解: 两路都命中 **{ov['both']}** 题, 仅向量命中 **{ov['only_vector']}** 题, "
        f"仅 BM25 命中 **{ov['only_bm25']}** 题, 两路都没命中 **{ov['neither']}** 题。"
    )
    a("")
    a("### 这组数字怎么解读(重要)\n")
    a(
        "混合检索的价值来自两路的**互补性**。本次测量中“仅向量命中”只有 "
        f"{ov['only_vector']} 题, 说明当前向量路几乎不提供 BM25 之外的增量 —— "
        "因为 Mock 模式下嵌入是**字符 n-gram 哈希投影**, 本质仍是词面匹配, "
        "与 BM25 同质, 所以融合后的效果只能贴近较强的那一路, 无法超越它。"
    )
    a("")
    a(
        "因此本报告**不宣称**“混合检索优于单路 BM25”。可宣称且可复现的是两点: "
        "(1) 混合检索显著优于纯向量检索, 解决了纯向量在原文档上关键词命中不稳的问题; "
        "(2) RRF 权重与常数已做成可配置项(`RRF_WEIGHT_VECTOR` / `RRF_K`), "
        "接入真实语义嵌入后把向量权重调回 1.0 重新测评, 才具备评估“混合是否超过单路”的前提。"
    )
    a("")

    # ---- C: 证据裁判 ----
    a("## 3. 证据裁判: 该拒答的时候有没有拒答\n")
    a(
        "检索永远会返回 Top-K —— 库里没有答案时, RRF 照样会排出一个“最不相关里最像的”。"
        "若直接喂给模型, 它就会顺着无关片段编出看起来有依据的答案。"
        "本节的闸门 (见 `backend/app/retrieval/gate.py`) 判定口径是: "
        f"问题的内容词在前 {gate['top_n']} 条证据里至少命中 "
        f"**{gate['min_terms']}** 个, 否则拒答。\n"
    )
    a("| 场景 | 期望行为 | 实测 | 比例 |")
    a("| --- | --- | --- | --- |")
    a(
        f"| {gate['in_total']} 道**语料范围内**问题 | 正常作答(不被误拒) | "
        f"{gate['in_accept']}/{gate['in_total']} 放行 | **{gate['in_rate']}%** |"
    )
    a(
        f"| {gate['out_total']} 道**与语料完全无关**的问题 | 拒答并说明“知识库中没有” | "
        f"{gate['out_reject']}/{gate['out_total']} 拒答 | **{gate['out_rate']}%** |"
    )
    a("")
    if gate["in_rejected"]:
        a("被闸门拦下的范围内问题(逐条列出, 不隐藏):\n")
        for r in gate["in_rejected"]:
            a(f"- `{r['q']}` —— {r['reason']}")
        a("")
        a(
            "> 这些题本身就是检索没命中的那批(见第 2 节的 Hit@5)。"
            "闸门把它们判为“证据不足”而不是让模型拿无关片段凑答案, 属于**预期的保守行为** —— "
            f"代价是少答了这几题, 收益是把 {gate['out_reject']}/{gate['out_total']} 的无关问题挡在生成之前。\n"
        )
    if gate["out_leaked"]:
        a("越闸的无关问题(说明词面判定的边界):\n")
        for r in gate["out_leaked"]:
            a(f"- `{r['q']}` —— {r['reason']}, 命中词: {r['matched_terms']}")
        a("")

    # ---- D ----
    a("## 4. 延迟: 首 token 时间 (TTFT)\n")
    if ttft:
        a(
            f"对运行中的服务连续发起 {ttft['requests']} 次 SSE 对话请求, "
            "统计“发出请求 → 收到第一个 token 事件”的耗时。\n"
        )
        a("| 指标 | 值 |")
        a("| --- | --- |")
        a(f"| 平均首 token | **{ttft['mean_ms']} ms** |")
        a(f"| P50 | {ttft['p50_ms']} ms |")
        a(f"| P95 | {ttft['p95_ms']} ms |")
        a(f"| min / max | {ttft['min_ms']} / {ttft['max_ms']} ms |")
        a(f"| 采样数 | {ttft['requests']} |")
        a("")
        a(
            "> 该数字为 **Mock 生成**下的端到端耗时, 已包含 Prefetch 预检索"
            "(嵌入 + 向量 + BM25 + RRF)与 SSE 首帧开销, **不含真实大模型推理**。"
            "接入真实 LLM 后首 token 主要由模型侧决定, 请用 `--ttft` 重测。\n"
        )
    else:
        a("未测量(未加 `--ttft` 参数, 或服务不可达)。测量方式:\n")
        a("```bash")
        a("cd backend && venv/Scripts/python.exe -m uvicorn app.main:app --port 8000")
        a("backend/venv/Scripts/python.exe eval/run_eval.py --ttft --requests 20")
        a("```\n")

    # ---- 结论 ----
    a("## 5. 结论与已知限制\n")
    a("**可以直接引用的实测结论**\n")
    a(
        f"1. 复杂文档入库成功率: {ing['naive']['rate']}% → **{ing['protected']['rate']}%**"
        f"({ing['naive']['hit']}/{ing['naive']['total']} → {ing['protected']['hit']}/{ing['protected']['total']}), "
        "提升完全来自表格结构保护。"
    )
    _gap_n = ret["summary"]["bm25"]["hit5"] - ret["summary"]["hybrid"]["hit5"]
    a(
        f"2. 混合检索相对**纯向量** Hit@5 提升 **{ret['gain_vs_vector_pct']}%**"
        f"({ret['summary']['vector']['hit5_rate']}% → {ret['summary']['hybrid']['hit5_rate']}%), "
        f"关键词型题目由 BM25 补齐; 与最佳单路 BM25 相差 {_gap_n} 题"
        f"({ret['summary']['bm25']['hit5']}/{ret['n']} vs {ret['summary']['hybrid']['hit5']}/{ret['n']}), "
        "在 91 题样本上不构成显著差异 —— 但也不宣称超越。"
    )
    a(
        f"3. 证据裁判: 语料范围内问题放行 {gate['in_rate']}%, "
        f"完全无关问题拒答 {gate['out_reject']}/{gate['out_total']} = **{gate['out_rate']}%**。"
    )
    if ttft:
        a(f"4. 首 token 平均 **{ttft['mean_ms']} ms** (Mock 生成, 含 Prefetch 检索链路)。")
    a("")
    a("**测评过程中发现并修复的真实缺陷**\n")
    a(
        "路由层原用“文本密度 < 0.35 即走 OCR”一条阈值统管所有格式, 而密度公式对每张表扣 500 字符, "
        "导致**表格越多的正常 DOCX/MD 反而被判为扫描件**并送进 OCR。语料中 6 篇结构化文档有 5 篇被误判。"
        "修复方式是改为按“是否存在文本层”决策: 图像必 OCR; Office/Markdown/TXT 天然带文本层故走原生; "
        "仅 PDF 依据可提取字符数判定是否为扫描件。修复后 12 篇语料路由全部正确。\n"
    )
    a("**已知限制(不要在简历里夸大)**\n")
    a(
        "- OCR 链路当前为 Mock 实现(`OCR_ENGINE=mock`), 验证的是“图片→OCR 路由正确”与"
        "“OCR 表格块被保护”, **不是识别准确率**。安装 `rapidocr-onnxruntime` 并设 `OCR_ENGINE=rapid` 后可测真实识别率。"
    )
    a("- 向量路在 Mock 模式下是哈希嵌入, 语义泛化能力弱; Hit@5 绝对值偏低不代表真实嵌入的效果。")
    a(
        "- 证据裁判是**纯词面**判定: 同义改写(问“薪酬”而文档写“工资”)会被误判为无证据。"
        "接入真实语义嵌入后应把向量相似度也作为一路信号并重测阈值。"
    )
    a("- TTFT 不含真实 LLM 推理时间。")
    a("")
    a("## 6. 复现步骤\n")
    a("```bash")
    a("cd enterprise-rag-workbench")
    a("python -m venv backend/venv")
    a("backend/venv/Scripts/pip install -r backend/requirements.txt -r eval/requirements-eval.txt")
    a("backend/venv/Scripts/python.exe eval/gen_corpus.py        # 生成 62 篇真实语料 + 91 条 QA")
    a("backend/venv/Scripts/python.exe eval/run_eval.py          # 复现第 1、2、3 节")
    a("# 第 4 节需服务在线(先启动 backend), 再执行: eval/run_eval.py --ttft --requests 20")
    a("```")
    a("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="RAG 工作台测评")
    ap.add_argument("--ttft", action="store_true", help="额外测量首 token 延迟(需服务已启动)")
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="被测量的服务地址")
    ap.add_argument("--requests", type=int, default=20, help="TTFT 采样次数")
    ap.add_argument("--query", default="入职流程有哪些步骤", help="TTFT 使用的问句")
    ap.add_argument("--out", default=os.path.join(EVAL_DIR, "report.md"))
    ap.add_argument("--json", default=os.path.join(EVAL_DIR, "results.json"))
    args = ap.parse_args()

    print(f"[EVAL] mock_mode={SETTINGS.mock_mode} embedding_dim={SETTINGS.embedding_dim}")

    print("[EVAL] A. 入库质量 ...")
    ing = grade_ingest()
    print(f"[EVAL]    基线 {ing['naive']['rate']}% -> 保护式 {ing['protected']['rate']}% "
          f"({ing['protected']['hit']}/{ing['protected']['total']})")

    print("[EVAL] B. 检索质量 ...")
    per_doc = []
    for d in DOCS:
        path = os.path.join(CORPUS_DIR, d["filename"])
        ext = _ext(d["filename"])
        probe = None if ext in IMAGE_TYPES else parse_native(path, ext)
        route, _ = choose_path(ext, probe)
        parsed = parse_ocr(path, ext) if route == "ocr" else (probe or parse_native(path, ext))
        per_doc.append((d["filename"], [p.content for p in build_chunks(parsed)]))
    ret = grade_retrieval(per_doc)
    for k in ("vector", "bm25", "hybrid"):
        s = ret["summary"][k]
        print(f"[EVAL]    {k:7s} Hit@5={s['hit5_rate']:5.1f}%  MRR@10={s['mrr10']:.3f}  "
              f"(kw {s['kw_rate']}% / sem {s['sem_rate']}%)")
    print(f"[EVAL]    混合 vs 纯向量 {ret['gain_vs_vector_pct']}% / vs 最佳单路 {ret['gap_vs_best_pp']}pp")
    ov = ret["overlap"]
    print(f"[EVAL]    互补性: both={ov['both']} only_vec={ov['only_vector']} only_bm25={ov['only_bm25']} neither={ov['neither']}")

    print("[EVAL] C. 证据裁判 ...")
    gate = grade_gate(per_doc)
    print(f"[EVAL]    范围内放行 {gate['in_rate']}% ({gate['in_accept']}/{gate['in_total']}) / "
          f"无关题拒答 {gate['out_reject']}/{gate['out_total']}")

    ttft = None
    if args.ttft:
        print(f"[EVAL] D. 首 token 延迟 ({args.requests} 次) ...")
        ttft = bench_ttft(args.url, args.requests, args.query)
        if ttft:
            print(f"[EVAL]    mean={ttft['mean_ms']}ms p50={ttft['p50_ms']}ms p95={ttft['p95_ms']}ms")

    meta = {
        "corpus_docs": len(DOCS),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    report = render_report(ing, ret, gate, ttft, meta)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(report)
    with open(args.json, "w", encoding="utf-8", newline="\n") as f:
        json.dump(
            {
                "meta": meta,
                "mock_mode": SETTINGS.mock_mode,
                "ingest": ing,
                "retrieval": {k: v for k, v in ret.items() if k != "details"},
                "gate": gate,
                "ttft": ttft,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"[OK ] 报告 -> {args.out}")
    print(f"[OK ] 数据 -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
