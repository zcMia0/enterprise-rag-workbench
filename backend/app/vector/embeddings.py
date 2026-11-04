"""嵌入服务: 真实大模型嵌入 + 确定性 Mock 嵌入。

Mock 嵌入策略 (离线可跑, 且具备基础语义可分性):
- 用字符 n-gram (1~3) 哈希到 dim 维, 做加权累加 + L2 归一化。
- 相同/相近文本得到相近向量, 足以演示"向量检索"效果, 但不可用于真实评测。

真实嵌入: 走 OpenAI 兼容接口 (DashScope text-embedding-v3 等)。
"""
from __future__ import annotations

import hashlib
import math

from app.config import get_settings
from app.logging_config import get_logger

log = get_logger("embeddings", "EMBED")

_settings = get_settings()


class EmbeddingService:
    def __init__(self) -> None:
        self.dim = _settings.embedding_dim
        self._client = None
        self.mode = "mock"
        if not _settings.mock_mode and _settings.dashscope_api_key:
            try:
                from openai import OpenAI  # type: ignore

                self._client = OpenAI(
                    api_key=_settings.dashscope_api_key,
                    base_url=_settings.llm_base_url,
                )
                self.mode = "real"
                log.info(f"embedding provider = real ({_settings.embedding_model})")
            except Exception as exc:  # noqa: BLE001
                log.warning(f"embedding client init failed ({exc}); mock fallback")
                self.mode = "mock"
        else:
            log.info("embedding provider = mock (deterministic hash)")

    def embed(self, text: str) -> list[float]:
        if self.mode == "real" and self._client is not None:
            try:
                resp = self._client.embeddings.create(
                    model=_settings.embedding_model, input=text
                )
                return list(resp.data[0].embedding)
            except Exception as exc:  # noqa: BLE001
                log.warning(f"real embed failed ({exc}); mock fallback for this call")
        return self._mock_embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self.mode == "real" and self._client is not None and texts:
            try:
                resp = self._client.embeddings.create(
                    model=_settings.embedding_model, input=texts
                )
                return [list(d.embedding) for d in resp.data]
            except Exception as exc:  # noqa: BLE001
                log.warning(f"real embed batch failed ({exc}); mock fallback")
        return [self._mock_embed(t) for t in texts]

    # ---------------- 确定性 Mock 嵌入 ----------------
    def _mock_embed(self, text: str) -> list[float]:
        """确定性哈希嵌入: 与 BM25 共用同一套分词口径(CJK 二元组), 再做哈希投影。

        分词口径必须和 BM25 一致 —— 否则同一句话在两条检索路上被切成完全不同的词表,
        融合排序就成了"把两种互不相干的噪声平均", 实测会让混合检索低于单路。
        """
        from app.retrieval.bm25 import tokenize  # 延迟导入, 避免模块级循环引用

        vec = [0.0] * self.dim
        tokens = tokenize(text)
        if not tokens:
            return self._normalize(vec)
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            vec[h % self.dim] += 1.0
            # 英文/数字长词补字符 bigram, 增强词形相近(如 timeout / timeouts)的召回
            if len(tok) > 3 and tok.isascii():
                for i in range(len(tok) - 1):
                    bh = int(hashlib.md5(tok[i : i + 2].encode("utf-8")).hexdigest(), 16)
                    vec[bh % self.dim] += 0.3
        # 归一化 (避免长度主导相似度)
        return self._normalize(vec)

    @staticmethod
    def _normalize(vec: list[float]) -> list[float]:
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度。"""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
