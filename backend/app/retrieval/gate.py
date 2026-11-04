"""证据裁判 (Evidence Gate): 判断召回的证据能否支撑回答, 不能则拒答。

为什么需要这一层
----------------
检索永远会返回 Top-K —— 哪怕库里根本没有相关内容, RRF 也会把"最不相关里最像的"
排到第一位。若直接把 Top-K 塞进 prompt, 模型会顺着这些无关片段编出一个看起来
有依据的答案, 这是企业知识库最致命的失败模式(用户无法核对, 却敢采信)。

所以生成之前必须有一道闸门: **问题里的内容词, 在证据里到底命中了几个**。
命中不足就如实说"知识库中没有", 而不是让模型自由发挥。

判定口径
--------
1. 用与 BM25 完全相同的 CJK 二元组分词 (tokenize) 切问题;
2. 丢掉疑问词/虚词("怎么""什么""如何"…), 它们在任何问题里都出现, 不携带主题信息;
3. 只保留**语料词表里存在**的词 —— 语料里从未出现过的词(如"量子""纠缠")
   不可能被任何证据命中, 计进分母只会让所有问题看起来都很差, 故先剔除;
4. 在前 top_n 条证据的并集里统计命中的不同词数 `matched_terms`;
5. `matched_terms < evidence_min_terms` 即判定证据不足。

为什么用"命中词数"而不是"分数阈值"
------------------------------------
RRF 融合分是名次派生量, 与相关性无绝对标度; 向量分在 Mock 模式下是哈希投影,
没有可比基准。而"命中了几个问题里的实词"是**可解释、可复现、与嵌入模型无关**的量,
既能给人看, 又能在换模型后保持含义稳定。

局限: 这一步是纯词面判定, 同义改写(问"薪酬"而文档写"工资")会被误判为无证据。
接入真实语义嵌入后, 应把向量相似度也作为一路信号并重测阈值。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import get_settings
from app.retrieval.bm25 import tokenize

_settings = get_settings()

# 疑问词 / 功能词: 它们几乎出现在任何问题里, 对"这段话是否在讲这件事"没有信息量。
# 不过滤的话, "Python 怎么处理多线程" 会靠"怎么""处理"命中无关文档而被放行
# (实测漏放 1 例, 过滤后 10/10 拒答)。只滤疑问/虚词, 不动实词 —— 实词交给阈值判断。
_STOP_BIGRAMS = frozenset(
    {
        "怎么", "什么", "如何", "哪些", "多少", "为什", "么样", "怎样", "是否",
        "可以", "能否", "请问", "一下", "介绍", "一些", "有哪", "哪个",
        "我们", "你们", "他们", "这个", "那个", "需要", "应该",
    }
)


@dataclass
class GateDecision:
    """裁判结果。可直接打进日志/接口, 让"为什么拒答"可追溯。"""

    usable: bool
    matched_terms: list[str] = field(default_factory=list)
    query_terms: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def coverage(self) -> float:
        """命中词数 / 问题内容词数, 仅用于观察, 不作为判定依据。"""
        if not self.query_terms:
            return 0.0
        return len(self.matched_terms) / len(self.query_terms)

    def as_dict(self) -> dict:
        return {
            "usable": self.usable,
            "matched_terms": self.matched_terms,
            "query_terms": len(self.query_terms),
            "coverage": round(self.coverage, 3),
            "reason": self.reason,
        }


def judge_evidence(
    query: str,
    evidence,
    vocabulary: set[str] | dict[str, float],
    min_terms: int | None = None,
    top_n: int | None = None,
) -> GateDecision:
    """判断证据是否可用。

    Args:
        query: 用户问题。
        evidence: RetrievalHit 序列 (需有 .content 属性), 按融合分降序。
        vocabulary: 语料词表 (BM25 索引的 idf 字典即可, 只用到 key)。
        min_terms: 至少命中的内容词数, 默认取配置 evidence_min_terms。
        top_n: 只看前 N 条证据, 默认取配置 evidence_gate_top_n。

    Returns:
        GateDecision; usable=False 时应拒答而非生成。
    """
    min_terms = _settings.evidence_min_terms if min_terms is None else min_terms
    top_n = _settings.evidence_gate_top_n if top_n is None else top_n

    # 1) 问题内容词: 去重 + 丢掉疑问/虚词 + 只保留语料里真实存在的词
    q_terms = [
        t
        for t in dict.fromkeys(tokenize(query))
        if t in vocabulary and t not in _STOP_BIGRAMS
    ]

    if not q_terms:
        return GateDecision(
            usable=False,
            query_terms=[],
            reason="问题中没有语料可匹配的内容词",
        )

    # 2) 证据侧词集合 (只取前 top_n 条, 避免"凑巧出现在末尾凑数命中")
    ev_terms: set[str] = set()
    for hit in list(evidence)[:top_n]:
        ev_terms.update(tokenize(getattr(hit, "content", "") or ""))

    matched = [t for t in q_terms if t in ev_terms]

    if len(matched) < min_terms:
        return GateDecision(
            usable=False,
            matched_terms=matched,
            query_terms=q_terms,
            reason=f"命中内容词 {len(matched)} 个, 低于阈值 {min_terms}",
        )

    return GateDecision(
        usable=True,
        matched_terms=matched,
        query_terms=q_terms,
        reason=f"命中内容词 {len(matched)} 个",
    )
