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


def rrf_fuse(rank_lists: list[list[dict]], k: int | None = None) -> list[dict]:
    """融合多个排名列表。

    Args:
        rank_lists: 每个元素是一组按相关性降序的字典, 需含 'chunk_id' 键。
        k: RRF 常数 (默认取 settings.rrf_k)。
    Returns:
        融合后按 fused_score 降序的字典列表, 保留各来源原始分数到 meta。
    """
    k = k or _settings.rrf_k
    fused: dict[int, dict] = {}
    for rank_list in rank_lists:
        for rank, item in enumerate(rank_list, start=1):
            cid = item["chunk_id"]
            contrib = 1.0 / (k + rank)
            if cid not in fused:
                fused[cid] = {"chunk_id": cid, "fused_score": 0.0, "sources": {}}
            fused[cid]["fused_score"] += contrib
            # 记录各检索器原始分 (按来源名)
            src_name = item.get("source", "unknown")
            fused[cid]["sources"][src_name] = item.get("score", 0.0)
    result = sorted(fused.values(), key=lambda x: x["fused_score"], reverse=True)
    log.info(f"rrf fused {len(result)} candidates from {len(rank_lists)} rank lists")
    return result
