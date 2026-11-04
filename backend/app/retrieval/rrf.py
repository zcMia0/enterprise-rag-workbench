"""RRF (Reciprocal Rank Fusion) 融合排序。

公式: score = Σ 1 / (k + rank_i), 对多个检索器的排名做加权融合,
不依赖各检索器分数量纲是否一致, 鲁棒性高。

参考: Cormack et al. 2009 "Reciprocal Rank Fusion outperforms Condorcet".
"""
from __future__ import annotations

from app.config import get_settings
from app.logging_config import get_logger

log = get_logger("retrieval", "RRF")

_settings = get_settings()


def rrf_fuse(
    rank_lists: list[list[dict]],
    k: int | None = None,
    weights: list[float] | None = None,
) -> list[dict]:
    """融合多个排名列表。

    Args:
        rank_lists: 每个元素是一组按相关性降序的字典, 需含 'chunk_id' 键。
        k: RRF 常数 (默认取 settings.rrf_k)。k 应与候选列表长度同量级:
           通用取值 60 面向万级语料; 企业库单查询候选只有几十条时, k 过大会把
           排名差异抹平(1/61 ≈ 1/90), 等于各名次等权, 融合就失去意义。
        weights: 各检索器的权重(与 rank_lists 一一对应, 默认全 1.0)。
           两路质量不均衡时(例如向量路用的是弱嵌入), 等权融合会让弱路稀释强路,
           实测会把整体命中率拉低; 权重用于表达"我更信谁"。

    Returns:
        融合后按 fused_score 降序的字典列表, 保留各来源原始分数到 sources。
    """
    k = k or _settings.rrf_k
    if weights is None:
        weights = [1.0] * len(rank_lists)
    if len(weights) != len(rank_lists):
        raise ValueError(
            f"weights 长度({len(weights)})必须与 rank_lists 数量({len(rank_lists)})一致"
        )

    fused: dict[int, dict] = {}
    for weight, rank_list in zip(weights, rank_lists):
        for rank, item in enumerate(rank_list, start=1):
            cid = item["chunk_id"]
            contrib = weight / (k + rank)
            if cid not in fused:
                fused[cid] = {"chunk_id": cid, "fused_score": 0.0, "sources": {}}
            fused[cid]["fused_score"] += contrib
            # 记录各检索器原始分 (按来源名)
            src_name = item.get("source", "unknown")
            fused[cid]["sources"][src_name] = item.get("score", 0.0)
    result = sorted(fused.values(), key=lambda x: x["fused_score"], reverse=True)
    log.info(
        f"rrf fused {len(result)} candidates from {len(rank_lists)} rank lists "
        f"(k={k}, weights={weights})"
    )
    return result
