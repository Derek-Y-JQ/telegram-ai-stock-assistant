"""Tests for global stock symbol parsing (CN/HK/US) and async TTL cache."""

from __future__ import annotations

import pytest

from stock_bot.services.market_data import normalize_stock_code, parse_stock_symbol
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


@pytest.mark.parametrize(
    ("raw", "market_type", "code", "yf_symbol"),
    [
        ("600519", "CN", "600519", "600519.SS"),
        ("000001.SZ", "CN", "000001", "000001.SZ"),
        ("00700", "HK", "00700", "0700.HK"),
        ("0700.HK", "HK", "00700", "0700.HK"),
        ("hk09988", "HK", "09988", "9988.HK"),
        ("AAPL", "US", "AAPL", "AAPL"),
        ("nvda", "US", "NVDA", "NVDA"),
        ("BRK.B", "US", "BRK-B", "BRK-B"),
    ],
)
def test_parse_stock_symbol(raw: str, market_type: str, code: str, yf_symbol: str) -> None:
    cand = parse_stock_symbol(raw)
    assert cand is not None
    assert cand.market_type == market_type
    assert cand.code == code
    assert cand.yf_symbol == yf_symbol


def test_parse_non_symbol_returns_none() -> None:
    assert parse_stock_symbol("帮我分析一下茅台") is None
    assert parse_stock_symbol("1234") is None


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
