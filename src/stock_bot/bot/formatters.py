"""Safe Telegram HTML formatters and message chunking utilities for CN/HK/US markets."""

from __future__ import annotations

import html
import re

from stock_bot.models import (
    BriefSubscription,
    FinanceSummary,
    IndexQuote,
    NewsItem,
    PriceAlert,
    StockCandidate,
    StockQuote,
    TechnicalReport,
    WatchlistItem,
)

TELEGRAM_MAX_LEN = 4000

MARKET_BADGE = {"CN": "🇨🇳 A股", "HK": "🇭🇰 港股", "US": "🇺🇸 美股"}


def esc(text: object) -> str:
    return html.escape(str(text), quote=False)


def _fmt_num(val: float | None, suffix: str = "", digits: int = 2) -> str:
    if val is None:
        return "—"
    return f"{val:.{digits}f}{suffix}"


def _fmt_change(pct: float, amt: float | None = None) -> str:
    icon = "🔴" if pct > 0 else ("🟢" if pct < 0 else "⚪")
    sign = "+" if pct > 0 else ""
    if amt is not None:
        return f"{icon} {sign}{pct:.2f}% ({sign}{amt:.2f})"
    return f"{icon} {sign}{pct:.2f}%"


def format_market_overview(indices: list[IndexQuote], include_tip: bool = True) -> str:
    if not indices:
        return "⚠️ 暂时无法获取大盘指数数据，请稍后重试。"

    lines = ["🌍 <b>全球核心大盘概览</b>", ""]
    groups = [
        ("CN", "🇨🇳 <b>A 股</b>"),
        ("HK", "🇭🇰 <b>港股</b>"),
        ("US", "🇺🇸 <b>美股</b>"),
    ]
    for m_type, header in groups:
        sub = [idx for idx in indices if idx.market_type == m_type]
        if not sub:
            continue
        lines.append(header)
        for idx in sub:
            lines.append(
                f"• <b>{esc(idx.name)}</b>  <code>{idx.close:.2f}</code>  {_fmt_change(idx.change_pct, idx.change_amount)}"
            )
        lines.append("")

    if include_tip:
        lines.append(
            "💡 <i>直接发代码（如 <code>600519</code>、<code>00700</code>、<code>NVDA</code>）看交互卡片，或直接用自然语言提问！</i>"
        )
    return "\n".join(lines).strip()


def format_stock_quote(quote: StockQuote) -> str:
    badge = MARKET_BADGE.get(quote.market_type, quote.market_type)
    header = f"📈 <b>{esc(quote.name)}</b> (<code>{esc(quote.ts_code)}</code>)  [{badge}]"
    meta_parts = [p for p in (quote.industry, quote.currency) if p]
    meta = f"🏷 {' · '.join(esc(p) for p in meta_parts)}" if meta_parts else ""

    amount_yi = quote.amount / 1e8 if quote.amount else 0.0
    lines = [header]
    if meta:
        lines.append(meta)
    lines.extend(
        [
            f"📅 交易日：<code>{esc(quote.trade_date)}</code>",
            "",
            f"<b>最新价：<code>{quote.close:.2f} {esc(quote.currency)}</code></b>  {_fmt_change(quote.change_pct, quote.change_amount)}",
            f"开盘：<code>{quote.open:.2f}</code>  最高：<code>{quote.high:.2f}</code>  最低：<code>{quote.low:.2f}</code>",
            f"成交额：<code>{amount_yi:.2f} 亿</code>  换手率：<code>{_fmt_num(quote.turnover_rate, '%')}</code>",
        ]
    )

    val_parts: list[str] = []
    if quote.total_mv is not None:
        val_parts.append(f"总市值 <code>{quote.total_mv:.1f} 亿</code>")
    if quote.pe_ttm is not None:
        val_parts.append(f"PE(TTM) <code>{quote.pe_ttm:.2f}</code>")
    if quote.pb is not None:
        val_parts.append(f"PB <code>{quote.pb:.2f}</code>")
    if val_parts:
        lines.append("估值：" + " · ".join(val_parts))

    lines.append("\n<i>点击下方按钮查看 K 线、技术诊断、财务、舆情或生成 AI 深度研报 👇</i>")
    return "\n".join(lines)


def format_finance(fin: FinanceSummary) -> str:
    badge = MARKET_BADGE.get(fin.market_type, fin.market_type)
    lines = [
        f"💰 <b>{esc(fin.name)}</b> (<code>{esc(fin.code)}</code>) 财务体检  [{badge}]",
        f"📅 报告期：<code>{esc(fin.report_date or '最新')}</code>  币种：<code>{esc(fin.currency)}</code>",
        "",
        f"• 每股收益 (EPS)：<code>{_fmt_num(fin.eps)}</code>",
        f"• 净资产收益率 (ROE)：<code>{_fmt_num(fin.roe, '%')}</code>",
        f"• 每股净资产 (BPS)：<code>{_fmt_num(fin.bps)}</code>",
        f"• 销售毛利率：<code>{_fmt_num(fin.gross_margin, '%')}</code>",
        f"• 销售净利率：<code>{_fmt_num(fin.net_margin, '%')}</code>",
        f"• 营收同比增速：<code>{_fmt_num(fin.revenue_yoy, '%')}</code>",
        f"• 净利同比增速：<code>{_fmt_num(fin.profit_yoy, '%')}</code>",
        f"• 负债率 / D/E：<code>{_fmt_num(fin.debt_to_assets, '%')}</code>",
        f"• 流动比率：<code>{_fmt_num(fin.current_ratio)}</code>",
    ]
    if fin.pe_ttm is not None or fin.pb is not None:
        lines.append(f"• 估值：PE(TTM) <code>{_fmt_num(fin.pe_ttm)}</code> | PB <code>{_fmt_num(fin.pb)}</code>")
    return "\n".join(lines)


def format_news(candidate: StockCandidate, items: list[NewsItem]) -> str:
    if not items:
        return f"📰 暂未找到 <b>{esc(candidate.name)}</b> (<code>{esc(candidate.ts_code)}</code>) 的近期新闻。"

    lines = [f"📰 <b>{esc(candidate.name)}</b> (<code>{esc(candidate.ts_code)}</code>) 最新资讯", ""]
    for i, item in enumerate(items[:6], start=1):
        title_html = (
            f'<a href="{html.escape(item.url, quote=True)}">{esc(item.title)}</a>'
            if item.url
            else esc(item.title)
        )
        meta = " · ".join(p for p in (item.source, item.publish_time) if p)
        lines.append(f"{i}. {title_html}")
        if meta:
            lines.append(f"   <i>{esc(meta)}</i>")
    return "\n".join(lines)


def format_technical_report(report: TechnicalReport) -> str:
    score_bar_filled = round(report.score / 10)
    score_bar = "█" * score_bar_filled + "░" * (10 - score_bar_filled)

    status_icon = {"bullish": "🔴", "bearish": "🟢", "neutral": "⚪"}
    lines = [
        f"📐 <b>{esc(report.name)}</b> (<code>{esc(report.code)}</code>) 量化技术诊断",
        f"📅 交易日：<code>{esc(report.trade_date)}</code>  收盘：<code>{report.latest_close:.2f}</code>",
        "",
        f"🎯 <b>综合评分：{report.score}/100（{esc(report.rating)}）</b>",
        f"<code>[{score_bar}]</code>",
        "",
        "<b>核心指标：</b>",
        f"• 均线：MA5 <code>{_fmt_num(report.ma5)}</code> | MA10 <code>{_fmt_num(report.ma10)}</code> | MA20 <code>{_fmt_num(report.ma20)}</code> | MA60 <code>{_fmt_num(report.ma60)}</code>",
        f"• MACD：DIF <code>{_fmt_num(report.macd_dif)}</code> | DEA <code>{_fmt_num(report.macd_dea)}</code> | 柱 <code>{_fmt_num(report.macd_hist)}</code>",
        f"• 强弱：RSI(14) <code>{_fmt_num(report.rsi14)}</code> | KDJ <code>{_fmt_num(report.kdj_k, '', 1)}/{_fmt_num(report.kdj_d, '', 1)}/{_fmt_num(report.kdj_j, '', 1)}</code>",
        f"• 区间：支撑 <code>{_fmt_num(report.support_level)}</code> | 阻力 <code>{_fmt_num(report.resistance_level)}</code> | 20日年化波动 <code>{_fmt_num(report.volatility_20d, '%')}</code>",
        "",
        "<b>信号明细：</b>",
    ]
    for sig in report.signals:
        icon = status_icon.get(sig.status, "⚪")
        lines.append(f"{icon} <b>{esc(sig.name)}</b>：{esc(sig.detail)}")

    lines.append("\n⚠️ <i>量化技术指标基于历史价格计算，仅供参考，不构成投资建议。</i>")
    return "\n".join(lines)


def format_watchlist(items: list[WatchlistItem]) -> str:
    if not items:
        return (
            "⭐ <b>我的自选股</b>\n\n"
            "当前自选列表为空。\n"
            "发送任意 A 股 / 港股 / 美股代码（如 <code>600519</code>、<code>00700</code>、<code>NVDA</code>），点击「⭐ 加自选」即可添加。"
        )

    lines = [f"⭐ <b>我的自选股</b>（共 {len(items)} 只）", ""]
    for item in items:
        badge = MARKET_BADGE.get(item.market_type, item.market_type)
        lines.append(f"• [{badge}] <b>{esc(item.name)}</b> (<code>{esc(item.code)}</code>)")
    lines.append("\n<i>点击下方按钮快速查看行情与分析 👇</i>")
    return "\n".join(lines)


def format_brief_status(sub: BriefSubscription, morning_time: str, evening_time: str) -> str:
    m_state = "✅ 已开启" if sub.morning_enabled else "⬜ 未开启"
    e_state = "✅ 已开启" if sub.evening_enabled else "⬜ 未开启"
    return (
        "⏰ <b>定时早晚报订阅中心</b>\n\n"
        f"• ☀️ <b>盘前早报</b>（工作日 <code>{esc(morning_time)}</code>）：{m_state}\n"
        f"• 🌙 <b>盘后晚报</b>（工作日 <code>{esc(evening_time)}</code>）：{e_state}\n\n"
        "内容包含：全球大盘（A股/港股/美股）+ 你的自选股涨跌 + AI 简评。\n"
        "<i>点击下方按钮一键开关或立即预览 👇</i>"
    )


def format_alerts(alerts: list[PriceAlert]) -> str:
    if not alerts:
        return (
            "🔔 <b>价格预警列表</b>\n\n"
            "当前没有生效中的价格预警。\n"
            "使用示例：\n"
            "• <code>/alert 600519 &gt; 1600</code>（突破 1600 提醒）\n"
            "• <code>/alert NVDA &lt; 120</code>（跌破 120 提醒）"
        )

    lines = [f"🔔 <b>生效中的价格预警</b>（共 {len(alerts)} 条）", ""]
    for a in alerts:
        sym = "≥" if a.direction == "above" else "≤"
        lines.append(
            f"• <code>#{a.id}</code> <b>{esc(a.name)}</b> (<code>{esc(a.code)}</code>)  {sym} <code>{a.target_price:.2f}</code>"
        )
    lines.append("\n<i>发送 <code>/alert del 编号</code> 或点击下方按钮删除预警。</i>")
    return "\n".join(lines)


def markdown_to_telegram_html(text: str) -> str:
    """Convert common LLM Markdown output into safe Telegram HTML without breaking on stray symbols."""
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"(?m)^#{1,6}\s+(.+)$", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", escaped)
    return escaped


def split_message(text: str, max_len: int = TELEGRAM_MAX_LEN) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        split_at = remaining.rfind("\n\n", 0, max_len)
        if split_at == -1:
            split_at = remaining.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
