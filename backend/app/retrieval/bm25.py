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

_ASCII_RE = re.compile(r"[a-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """分词: 英文/数字按词切, 中文按**二元组(bigram)**切。

    中文没有空格, 若把一串汉字当成单个 token, 查询里的"工号的格式要求"与文档里的
    "工号, 格式 EB-2024-0001" 永远匹配不上 —— 实测会让 BM25 的中文命中率跌到 20% 以下。
    这里采用 Lucene CJKAnalyzer 的经典做法: 汉字串切成相邻两字组合(单字串单独保留),
    既不需要词典/分词模型, 又能让"工号""格式""要求"这类词面真正命中。
    """
    t = (text or "").lower()
    tokens = _ASCII_RE.findall(t)
    for run in _CJK_RE.findall(t):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


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
