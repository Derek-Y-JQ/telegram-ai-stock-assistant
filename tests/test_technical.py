"""Tests for the quantitative TechnicalAnalyzer."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_bot.services.technical import TechnicalAnalyzer


def _make_ohlcv(prices: np.ndarray) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=len(prices))
    return pd.DataFrame(
        {
            "Open": prices * 0.995,
            "High": prices * 1.015,
            "Low": prices * 0.985,
            "Close": prices,
            "Volume": np.full(len(prices), 1_000_000.0),
        },
        index=dates,
    )


def test_technical_uptrend_scores_bullish() -> None:
    prices = np.linspace(100.0, 145.0, 90)
    df = _make_ohlcv(prices)
    report = TechnicalAnalyzer.analyze("600519", "贵州茅台", df)

    assert report.code == "600519"
    assert report.score >= 60
    assert report.ma5 is not None and report.ma20 is not None and report.ma5 > report.ma20
    assert report.support_level is not None and report.resistance_level is not None
    assert report.resistance_level > report.support_level
    assert len(report.signals) >= 4


def test_technical_downtrend_scores_bearish() -> None:
    prices = np.linspace(150.0, 95.0, 90)
    df = _make_ohlcv(prices)
    report = TechnicalAnalyzer.analyze("000001", "平安银行", df)

    assert report.score <= 45
    assert report.ma5 is not None and report.ma20 is not None and report.ma5 < report.ma20


def test_technical_insufficient_data_raises() -> None:
    df = _make_ohlcv(np.linspace(10.0, 12.0, 10))
    with pytest.raises(ValueError):
        TechnicalAnalyzer.analyze("000001", "测试", df)
