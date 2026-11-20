"""Professional A-share K-line chart renderer powered by mplfinance."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

logger = logging.getLogger(__name__)

_CJK_FONT_CANDIDATES = (
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "SimHei",
    "PingFang SC",
    "Microsoft YaHei",
    "Source Han Sans CN",
)


def _detect_cjk_font() -> str | None:
    installed = {f.name for f in fm.fontManager.ttflist}
    for candidate in _CJK_FONT_CANDIDATES:
        if candidate in installed:
            return candidate
    return None


class ChartService:
    """Renders A-share style (red up / green down) candlestick charts with MA, Volume, and MACD."""

    def __init__(self) -> None:
        self._font = _detect_cjk_font()

    async def render_kline(
        self,
        df: pd.DataFrame,
        code: str,
        name: str,
        period: Literal["daily", "weekly", "monthly"] = "daily",
        bars: int = 90,
    ) -> bytes:
        return await asyncio.to_thread(self._render_sync, df, code, name, period, bars)

    def _render_sync(
        self,
        df: pd.DataFrame,
        code: str,
        name: str,
        period: Literal["daily", "weekly", "monthly"],
        bars: int,
    ) -> bytes:
        if df.empty:
            raise ValueError("无法绘制空行情数据。")

        full = df.copy().sort_index()
        close = full["Close"].astype(float)

        # Compute indicators on full series before slicing visible window
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        hist = (dif - dea) * 2.0

        full["MA5"] = close.rolling(5).mean()
        full["MA10"] = close.rolling(10).mean()
        full["MA20"] = close.rolling(20).mean()
        full["MA60"] = close.rolling(60).mean()
        full["DIF"] = dif
        full["DEA"] = dea
        full["HIST"] = hist

        plot_df = full.tail(bars).copy()

        # A-share convention: red for up, green for down
        market_colors = mpf.make_marketcolors(
            up="#ef5350",
            down="#26a69a",
            edge="inherit",
            wick="inherit",
            volume="inherit",
        )
        rc_params: dict[str, object] = {"axes.unicode_minus": False}
        if self._font:
            rc_params["font.sans-serif"] = [self._font, "DejaVu Sans"]

        style = mpf.make_mpf_style(
            base_mpf_style="yahoo",
            marketcolors=market_colors,
            facecolor="#ffffff",
            figcolor="#ffffff",
            gridcolor="#e9ecef",
            gridstyle="--",
            rc=rc_params,
        )

        add_plots: list[object] = []
        for col, color in (
            ("MA5", "#ff9800"),
            ("MA10", "#2196f3"),
            ("MA20", "#9c27b0"),
            ("MA60", "#607d8b"),
        ):
            if plot_df[col].notna().any():
                add_plots.append(mpf.make_addplot(plot_df[col], color=color, width=1.1))

        # MACD panel (panel=2)
        hist_pos = plot_df["HIST"].where(plot_df["HIST"] >= 0, 0.0)
        hist_neg = plot_df["HIST"].where(plot_df["HIST"] < 0, 0.0)
        add_plots.extend(
            [
                mpf.make_addplot(plot_df["DIF"], panel=2, color="#ff9800", width=1.0, ylabel="MACD"),
                mpf.make_addplot(plot_df["DEA"], panel=2, color="#2196f3", width=1.0),
                mpf.make_addplot(hist_pos, panel=2, type="bar", color="#ef5350", alpha=0.7),
                mpf.make_addplot(hist_neg, panel=2, type="bar", color="#26a69a", alpha=0.7),
            ]
        )

        period_label = {"daily": "日K", "weekly": "周K", "monthly": "月K"}[period]
        title = (
            f"{name} ({code}) · {period_label}"
            if self._font
            else f"{code} · {period.capitalize()} K-Line"
        )

        fig, _ = mpf.plot(
            plot_df[["Open", "High", "Low", "Close", "Volume"]],
            type="candle",
            style=style,
            volume=True,
            addplot=add_plots,
            panel_ratios=(5, 2, 2),
            figsize=(11, 7),
            title=title,
            ylabel="Price",
            ylabel_lower="Volume",
            datetime_format="%Y-%m-%d",
            xrotation=20,
            returnfig=True,
            tight_layout=True,
        )

        buf = io.BytesIO()
        try:
            fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
            buf.seek(0)
            return buf.getvalue()
        finally:
            plt.close(fig)
