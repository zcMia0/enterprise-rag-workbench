"""应用层 BM25 检索 (内存索引)。

为何需要 BM25: 向量检索对"标题词 / 字段名 / 课程名 / 表格字段"等精确关键词命中率偏低,
BM25 做词面匹配补足, 再用 RRF 与向量分融合。

索引在内存维护, 启动/重建时由 retrieval_service 灌入全部未删除 chunk 文本。
多进程场景可换 Elasticsearch/Whoosh, 接口保持一致。
"""
from __future__ import annotations

import math
import re
from collections import Counter

from app.logging_config import get_logger

log = get_logger("retrieval", "BM25")

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs: dict[int, list[str]] = {}
        self.doc_freqs: dict[int, Counter] = {}
        self.idf: dict[str, float] = {}
        self.doc_len: dict[int, int] = {}
        self.avg_len = 0.0
        self._built = False

    def index(self, chunk_id: int, content: str) -> None:
        toks = tokenize(content)
        self.docs[chunk_id] = toks
        self.doc_freqs[chunk_id] = Counter(toks)
        self.doc_len[chunk_id] = len(toks)

    def build(self) -> None:
        if not self.docs:
            self._built = True
            return
        n = len(self.docs)
        df: Counter = Counter()
        for freqs in self.doc_freqs.values():
            for term in freqs:
                df[term] += 1
        self.idf = {
            term: math.log(1 + (n - d + 0.5) / (d + 0.5)) for term, d in df.items()
        }
        self.avg_len = sum(self.doc_len.values()) / n
        self._built = True
        log.info(f"bm25 index built ({n} docs)")

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        if not self._built:
            self.build()
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scores: dict[int, float] = {}
        for qt in q_tokens:
            idf = self.idf.get(qt)
            if idf is None:
                continue
            for cid, toks in self.docs.items():
                # 词频 (该 chunk 是否含该词)
                if qt not in self.doc_freqs[cid]:
                    continue
                tf = self.doc_freqs[cid][qt]
                dl = self.doc_len[cid]
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self.avg_len or 1))
                scores[cid] = scores.get(cid, 0.0) + idf * (tf * (self.k1 + 1) / denom)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [{"chunk_id": cid, "score": s} for cid, s in ranked]

    def remove(self, chunk_id: int) -> None:
        self.docs.pop(chunk_id, None)
        self.doc_freqs.pop(chunk_id, None)
        self.doc_len.pop(chunk_id, None)
        self._built = False
