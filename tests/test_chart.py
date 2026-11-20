"""Tests for mplfinance ChartService."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stock_bot.services.chart import ChartService


async def test_render_kline_returns_valid_png_and_closes_figures() -> None:
    dates = pd.bdate_range("2026-01-01", periods=80)
    base = np.linspace(50.0, 72.0, 80) + np.sin(np.linspace(0, 8, 80)) * 2.0
    df = pd.DataFrame(
        {
            "Open": base * 0.99,
            "High": base * 1.02,
            "Low": base * 0.98,
            "Close": base,
            "Volume": np.linspace(500_000, 1_500_000, 80),
        },
        index=dates,
    )

    service = ChartService()
    before_figs = len(plt.get_fignums())
    png_bytes = await service.render_kline(df, "600519", "贵州茅台", period="daily", bars=60)
    after_figs = len(plt.get_fignums())

    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png_bytes) > 5000
    assert after_figs == before_figs
