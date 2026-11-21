"""Tests for Telegram HTML formatters and chunking."""

from __future__ import annotations

from stock_bot.bot.formatters import (
    format_stock_quote,
    markdown_to_telegram_html,
    split_message,
)
from stock_bot.models import StockQuote


def test_markdown_to_telegram_html_escapes_unsafe_chars() -> None:
    raw = "### 结论\n**贵州茅台** <PE> & `600519`"
    converted = markdown_to_telegram_html(raw)
    assert "<b>结论</b>" in converted
    assert "<b>贵州茅台</b>" in converted
    assert "&lt;PE&gt; &amp;" in converted
    assert "<code>600519</code>" in converted


def test_split_message_respects_limit() -> None:
    text = "\n\n".join(["段落内容 " + ("A" * 100)] * 50)
    chunks = split_message(text, max_len=500)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)


def test_format_stock_quote() -> None:
    quote = StockQuote(
        code="600519",
        ts_code="600519.SH",
        name="贵州茅台",
        market="SH",
        industry="酿酒行业",
        trade_date="2026-11-20",
        open=1500.0,
        close=1525.5,
        high=1530.0,
        low=1495.0,
        pre_close=1500.0,
        change_pct=1.7,
        change_amount=25.5,
        volume=20000.0,
        amount=3_050_000_000.0,
        turnover_rate=0.16,
        total_mv=19160.5,
    )
    rendered_en = format_stock_quote(quote)
    assert "贵州茅台" in rendered_en
    assert "600519.SH" in rendered_en
    assert "🟢 +1.70%" in rendered_en

    rendered_zh = format_stock_quote(quote, lang="zh")
    assert "🔴 +1.70%" in rendered_zh
