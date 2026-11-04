"""结构化日志配置。

统一输出格式: [%(asctime)s] [%(levelname)s] [%(name)s] [阶段标签] 消息
示例: [2026-11-04 10:00:00] [INFO] [retriever] [HYBRID] hybrid retrieval started

为便于演示与面试讲解, 关键链路(检索 / 证据裁判 / 缓存命中 / 安全拦截 / 切分)
都使用统一的 get_logger(module, stage) 入口打点。
"""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def configure_logging(level: str = "INFO") -> None:
    """全局仅配置一次根日志。"""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    _CONFIGURED = True


def get_logger(module: str, stage: str | None = None) -> logging.LoggerAdapter:
    """获取带阶段的日志适配器。

    Args:
        module: 模块名, 如 retriever / chunker / agent / parser
        stage:  阶段标签, 如 HYBRID / PREFETCH / EVIDENCE / CACHE / SAFETY / SPLIT
    """
    logger = logging.getLogger(module)
    if stage:
        return logging.LoggerAdapter(logger, {"stage": stage})
    return logging.LoggerAdapter(logger, {})


# 让 LoggerAdapter 自动把 stage 注入消息前缀
_orig_process = logging.LoggerAdapter.process


def _process(self, msg, kwargs):  # type: ignore[no-untyped-def]
    stage = self.extra.get("stage") if self.extra else None
    if stage:
        return f"[{stage}] {msg}", kwargs
    return msg, kwargs


logging.LoggerAdapter.process = _process  # type: ignore[assignment]
