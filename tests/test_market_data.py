"""Tests for stock code normalization and async TTL cache."""

from __future__ import annotations

import pytest

from stock_bot.services.market_data import normalize_stock_code
from stock_bot.storage.cache import AsyncTTLCache


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("600519", ("600519", "600519.SH", "sh600519")),
        ("600519.SH", ("600519", "600519.SH", "sh600519")),
        ("sh600519", ("600519", "600519.SH", "sh600519")),
        ("000001", ("000001", "000001.SZ", "sz000001")),
        ("300750.sz", ("300750", "300750.SZ", "sz300750")),
        ("830799", ("830799", "830799.BJ", "bj830799")),
        ("430047.BJ", ("430047", "430047.BJ", "bj430047")),
        ("920001", ("920001", "920001.BJ", "bj920001")),
    ],
)
def test_normalize_stock_code(raw: str, expected: tuple[str, str, str]) -> None:
    assert normalize_stock_code(raw) == expected


def test_normalize_invalid_code() -> None:
    with pytest.raises(ValueError):
        normalize_stock_code("AAPL")
    with pytest.raises(ValueError):
        normalize_stock_code("12345")


async def test_async_ttl_cache() -> None:
    cache = AsyncTTLCache(default_ttl=60)
    calls = 0

    async def factory() -> str:
        nonlocal calls
        calls += 1
        return "value"

    v1 = await cache.get_or_set("k1", factory)
    v2 = await cache.get_or_set("k1", factory)
    assert v1 == v2 == "value"
    assert calls == 1

    await cache.clear()
    assert await cache.get("k1") is None
