"""Coalesce identical in-flight catalog requests (dedupe thundering herd)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

_lock = asyncio.Lock()
_inflight: dict[str, asyncio.Future] = {}


async def coalesce(
    key: str,
    factory: Callable[[], Awaitable[T]],
) -> T:
    """
    If `key` is already being resolved, await the same Future.
    Otherwise run `factory()` once and share the result.
    """
    async with _lock:
        fut = _inflight.get(key)
        if fut is None:
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            _inflight[key] = fut

            async def _runner() -> None:
                try:
                    result = await factory()
                    if not fut.done():
                        fut.set_result(result)
                except Exception as exc:
                    if not fut.done():
                        fut.set_exception(exc)
                finally:
                    async with _lock:
                        if _inflight.get(key) is fut:
                            _inflight.pop(key, None)

            asyncio.create_task(_runner())

    return await fut
