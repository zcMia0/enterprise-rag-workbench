"""Redis 客户端 (含 Mock 降级)。

作用: 会话线程缓存、Agent 短期记忆、检索结果缓存、限流等。
降级: 连不上 Redis 时, 使用进程内字典 (单进程可用, 重启即丢),
      保证项目在无 Redis 环境也能完整运行。多进程/生产请务必启用真实 Redis。
"""
from __future__ import annotations

import threading
from typing import Any

from app.config import get_settings
from app.logging_config import get_logger

log = get_logger("redis", "INIT")

_settings = get_settings()


class _InMemoryKV:
    """极简内存 KV, 仅用于无 Redis 的本地降级。"""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._locks: dict[str, float] = {}
        self._mu = threading.Lock()

    def ping(self) -> bool:
        return True

    def get(self, key: str) -> Any | None:
        with self._mu:
            return self._store.get(key)

    def set(self, key: str, value: Any, ex: int | None = None) -> None:
        with self._mu:
            self._store[key] = value
            if ex is not None:
                # 简化: 不实现真实过期调度, 仅记录
                self._locks[key] = ex

    def delete(self, key: str) -> None:
        with self._mu:
            self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        with self._mu:
            return key in self._store

    def incr(self, key: str) -> int:
        with self._mu:
            self._store[key] = int(self._store.get(key, 0)) + 1
            return self._store[key]

    def expire(self, key: str, ex: int) -> None:  # noqa: ARG002
        with self._mu:
            self._locks[key] = ex


class RedisClient:
    """统一封装, 内部自动选择真实 Redis 或内存降级。"""

    def __init__(self) -> None:
        self._real = None
        self._mock = _InMemoryKV()
        self.using_mock = True
        self._try_connect()

    def _try_connect(self) -> None:
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(
                _settings.redis_url, socket_connect_timeout=2, decode_responses=True
            )
            client.ping()
            self._real = client
            self.using_mock = False
            log.info(f"redis connected -> {_settings.redis_url}")
        except Exception as exc:  # noqa: BLE001
            self._real = None
            self.using_mock = True
            log.warning(f"redis unreachable ({exc}); using in-memory fallback")

    # ---- 代理 API ----
    def ping(self) -> bool:
        if self._real:
            try:
                return bool(self._real.ping())
            except Exception:  # noqa: BLE001
                return False
        return self._mock.ping()

    def get(self, key: str) -> Any | None:
        return self._real.get(key) if self._real else self._mock.get(key)

    def set(self, key: str, value: Any, ex: int | None = None) -> None:
        if self._real:
            self._real.set(key, value, ex=ex)
        else:
            self._mock.set(key, value, ex=ex)

    def delete(self, key: str) -> None:
        if self._real:
            self._real.delete(key)
        else:
            self._mock.delete(key)

    def exists(self, key: str) -> bool:
        return bool(self._real.exists(key)) if self._real else self._mock.exists(key)

    def incr(self, key: str) -> int:
        return int(self._real.incr(key)) if self._real else self._mock.incr(key)

    def expire(self, key: str, ex: int) -> None:
        if self._real:
            self._real.expire(key, ex)
        else:
            self._mock.expire(key, ex)


redis_client = RedisClient()
