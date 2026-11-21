"""Safe Telegram HTML formatters with full EN (default) / ZH bilingual support for US/SG/HK/CN markets."""

from __future__ import annotations

import html
import re

from stock_bot.i18n import localize_index_name, market_badge
from stock_bot.models import (
    BriefSubscription,
    FinanceSummary,
    IndexQuote,
    Lang,
    NewsItem,
    PriceAlert,
    StockCandidate,
    StockQuote,
    TechnicalReport,
    WatchlistItem,
)

TELEGRAM_MAX_LEN = 4000


def esc(text: object) -> str:
    return html.escape(str(text), quote=False)


def _fmt_num(val: float | None, suffix: str = "", digits: int = 2) -> str:
    if val is None:
        return "—"
    return f"{val:.{digits}f}{suffix}"


def _fmt_change(pct: float, amt: float | None = None, lang: Lang = "en") -> str:
    # Green up / Red down in English (international); Red up / Green down in Chinese
    if lang == "en":
        icon = "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")
    else:
        icon = "🔴" if pct > 0 else ("🟢" if pct < 0 else "⚪")
    sign = "+" if pct > 0 else ""
    if amt is not None:
        return f"{icon} {sign}{pct:.2f}% ({sign}{amt:.2f})"
    return f"{icon} {sign}{pct:.2f}%"


def format_market_overview(
    indices: list[IndexQuote],
    lang: Lang = "en",
    include_tip: bool = True,
) -> str:
    en = lang == "en"
    if not indices:
        return (
            "⚠️ Unable to fetch global index data right now. Please try again shortly."
            if en
            else "⚠️ 暂时无法获取大盘指数数据，请稍后重试。"
        )

    lines = ["🌍 <b>Global Market Overview</b>" if en else "🌍 <b>全球核心大盘概览</b>", ""]
    groups = (
        [
            ("US", "🇺🇸 <b>US Markets</b>"),
            ("SG", "🇸🇬 <b>Singapore (SGX)</b>"),
            ("HK", "🇭🇰 <b>Hong Kong</b>"),
            ("CN", "🇨🇳 <b>China A-Shares</b>"),
        ]
        if en
        else [
            ("US", "🇺🇸 <b>美股</b>"),
            ("SG", "🇸🇬 <b>新加坡</b>"),
            ("HK", "🇭🇰 <b>港股</b>"),
            ("CN", "🇨🇳 <b>A 股</b>"),
        ]
    )

    for m_type, header in groups:
        sub = [idx for idx in indices if idx.market_type == m_type]
        if not sub:
            continue
        lines.append(header)
        for idx in sub:
            disp_name = localize_index_name(idx.code, idx.name, lang)
            lines.append(
                f"• <b>{esc(disp_name)}</b>  <code>{idx.close:.2f}</code>  {_fmt_change(idx.change_pct, idx.change_amount, lang)}"
            )
        lines.append("")

    if include_tip:
        lines.append(
            "💡 <i>Send any ticker (<code>NVDA</code>, <code>D05.SI</code>, <code>00700</code>, <code>600519</code>) or ask a question in natural language.</i>"
            if en
            else "💡 <i>直接发代码（<code>NVDA</code>、<code>D05.SI</code>、<code>00700</code>、<code>600519</code>）看交互卡片，或直接用自然语言提问。</i>"
        )
    return "\n".join(lines).strip()


def format_stock_quote(quote: StockQuote, lang: Lang = "en") -> str:
    en = lang == "en"
    badge = market_badge(quote.market_type, lang)
    header = f"📈 <b>{esc(quote.name)}</b> (<code>{esc(quote.ts_code)}</code>)  [{badge}]"
    meta_parts = [p for p in (quote.industry, quote.currency) if p]
    meta = f"🏷 {' · '.join(esc(p) for p in meta_parts)}" if meta_parts else ""

    lines = [header]
    if meta:
        lines.append(meta)

    if en:
        vol_str = f"{quote.amount / 1e9:.2f}B" if quote.amount >= 1e9 else f"{quote.amount / 1e6:.2f}M"
        lines.extend(
            [
                f"📅 Date: <code>{esc(quote.trade_date)}</code>",
                "",
                f"<b>Price: <code>{quote.close:.2f} {esc(quote.currency)}</code></b>  {_fmt_change(quote.change_pct, quote.change_amount, lang)}",
                f"Open: <code>{quote.open:.2f}</code>  High: <code>{quote.high:.2f}</code>  Low: <code>{quote.low:.2f}</code>",
                f"Turnover: <code>{vol_str}</code>  Rate: <code>{_fmt_num(quote.turnover_rate, '%')}</code>",
            ]
        )
        val_parts: list[str] = []
        if quote.total_mv is not None:
            val_parts.append(f"Mkt Cap <code>{quote.total_mv / 10:.1f}B</code>")
        if quote.pe_ttm is not None:
            val_parts.append(f"PE(TTM) <code>{quote.pe_ttm:.2f}</code>")
        if quote.pb is not None:
            val_parts.append(f"PB <code>{quote.pb:.2f}</code>")
        if val_parts:
            lines.append("Valuation: " + " · ".join(val_parts))
        lines.append("\n<i>Tap below for K-line charts, technicals, financials, news, or AI brief 👇</i>")
    else:
        amount_yi = quote.amount / 1e8 if quote.amount else 0.0
        lines.extend(
            [
                f"📅 交易日：<code>{esc(quote.trade_date)}</code>",
                "",
                f"<b>最新价：<code>{quote.close:.2f} {esc(quote.currency)}</code></b>  {_fmt_change(quote.change_pct, quote.change_amount, lang)}",
                f"开盘：<code>{quote.open:.2f}</code>  最高：<code>{quote.high:.2f}</code>  最低：<code>{quote.low:.2f}</code>",
                f"成交额：<code>{amount_yi:.2f} 亿</code>  换手率：<code>{_fmt_num(quote.turnover_rate, '%')}</code>",
            ]
        )
        val_parts = []
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


def format_finance(fin: FinanceSummary, lang: Lang = "en") -> str:
    en = lang == "en"
    badge = market_badge(fin.market_type, lang)
    if en:
        lines = [
            f"💰 <b>{esc(fin.name)}</b> (<code>{esc(fin.code)}</code>) Financials  [{badge}]",
            f"📅 Period: <code>{esc(fin.report_date or 'Latest')}</code>  Currency: <code>{esc(fin.currency)}</code>",
            "",
            f"• EPS: <code>{_fmt_num(fin.eps)}</code>",
            f"• ROE: <code>{_fmt_num(fin.roe, '%')}</code>",
            f"• Book Value / Share: <code>{_fmt_num(fin.bps)}</code>",
            f"• Gross Margin: <code>{_fmt_num(fin.gross_margin, '%')}</code>",
            f"• Net Margin: <code>{_fmt_num(fin.net_margin, '%')}</code>",
            f"• Revenue Growth (YoY): <code>{_fmt_num(fin.revenue_yoy, '%')}</code>",
            f"• Earnings Growth (YoY): <code>{_fmt_num(fin.profit_yoy, '%')}</code>",
            f"• Debt Ratio / D/E: <code>{_fmt_num(fin.debt_to_assets, '%')}</code>",
            f"• Current Ratio: <code>{_fmt_num(fin.current_ratio)}</code>",
        ]
        if fin.pe_ttm is not None or fin.pb is not None:
            lines.append(f"• Valuation: PE(TTM) <code>{_fmt_num(fin.pe_ttm)}</code> | PB <code>{_fmt_num(fin.pb)}</code>")
        return "\n".join(lines)

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


def format_news(candidate: StockCandidate, items: list[NewsItem], lang: Lang = "en") -> str:
    en = lang == "en"
    if not items:
        return (
            f"📰 No recent news found for <b>{esc(candidate.name)}</b> (<code>{esc(candidate.ts_code)}</code>)."
            if en
            else f"📰 暂未找到 <b>{esc(candidate.name)}</b> (<code>{esc(candidate.ts_code)}</code>) 的近期新闻。"
        )

    header = (
        f"📰 <b>{esc(candidate.name)}</b> (<code>{esc(candidate.ts_code)}</code>) Latest News"
        if en
        else f"📰 <b>{esc(candidate.name)}</b> (<code>{esc(candidate.ts_code)}</code>) 最新资讯"
    )
    lines = [header, ""]
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


def format_technical_report(report: TechnicalReport, lang: Lang = "en") -> str:
    en = lang == "en"
    score_bar_filled = round(report.score / 10)
    score_bar = "█" * score_bar_filled + "░" * (10 - score_bar_filled)
    status_icon = (
        {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}
        if en
        else {"bullish": "🔴", "bearish": "🟢", "neutral": "⚪"}
    )

    if en:
        lines = [
            f"📐 <b>{esc(report.name)}</b> (<code>{esc(report.code)}</code>) Technical Diagnosis",
            f"📅 Date: <code>{esc(report.trade_date)}</code>  Close: <code>{report.latest_close:.2f}</code>",
            "",
            f"🎯 <b>Composite Score: {report.score}/100 ({esc(report.rating)})</b>",
            f"<code>[{score_bar}]</code>",
            "",
            "<b>Key Indicators:</b>",
            f"• MA: 5D <code>{_fmt_num(report.ma5)}</code> | 10D <code>{_fmt_num(report.ma10)}</code> | 20D <code>{_fmt_num(report.ma20)}</code> | 60D <code>{_fmt_num(report.ma60)}</code>",
            f"• MACD: DIF <code>{_fmt_num(report.macd_dif)}</code> | DEA <code>{_fmt_num(report.macd_dea)}</code> | Hist <code>{_fmt_num(report.macd_hist)}</code>",
            f"• Momentum: RSI(14) <code>{_fmt_num(report.rsi14)}</code> | KDJ <code>{_fmt_num(report.kdj_k, '', 1)}/{_fmt_num(report.kdj_d, '', 1)}/{_fmt_num(report.kdj_j, '', 1)}</code>",
            f"• Range: Support <code>{_fmt_num(report.support_level)}</code> | Resistance <code>{_fmt_num(report.resistance_level)}</code> | 20D Vol <code>{_fmt_num(report.volatility_20d, '%')}</code>",
            "",
            "<b>Signal Breakdown:</b>",
        ]
    else:
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
        sep = ": " if en else "："
        lines.append(f"{icon} <b>{esc(sig.name)}</b>{sep}{esc(sig.detail)}")

    lines.append(
        "\n⚠️ <i>Quantitative indicators are based on historical prices and do not constitute financial advice.</i>"
        if en
        else "\n⚠️ <i>量化技术指标基于历史价格计算，仅供参考，不构成投资建议。</i>"
    )
    return "\n".join(lines)


def format_watchlist(items: list[WatchlistItem], lang: Lang = "en") -> str:
    en = lang == "en"
    if not items:
        return (
            "⭐ <b>My Watchlist</b>\n\n"
            "Your watchlist is empty.\n"
            "Send any ticker (<code>NVDA</code>, <code>D05.SI</code>, <code>00700</code>, <code>600519</code>) and tap 'Add Watchlist'."
            if en
            else "⭐ <b>我的自选股</b>\n\n"
            "当前自选列表为空。\n"
            "发送任意美股 / 新加坡 / 港股 / A股代码（如 <code>NVDA</code>、<code>D05.SI</code>、<code>00700</code>、<code>600519</code>），点击「⭐ 加自选」即可添加。"
        )

    lines = [
        f"⭐ <b>My Watchlist</b> ({len(items)} stocks)" if en else f"⭐ <b>我的自选股</b>（共 {len(items)} 只）",
        "",
    ]
    for item in items:
        badge = market_badge(item.market_type, lang)
        lines.append(f"• [{badge}] <b>{esc(item.name)}</b> (<code>{esc(item.code)}</code>)")
    lines.append("\n<i>Tap a ticker below to open its quote card 👇</i>" if en else "\n<i>点击下方按钮快速查看行情与分析 👇</i>")
    return "\n".join(lines)


def format_brief_status(
    sub: BriefSubscription,
    morning_time: str,
    evening_time: str,
    lang: Lang = "en",
) -> str:
    en = lang == "en"
    if en:
        m_state = "✅ Enabled" if sub.morning_enabled else "⬜ Off"
        e_state = "✅ Enabled" if sub.evening_enabled else "⬜ Off"
        return (
            "⏰ <b>Daily Market Briefings</b>\n\n"
            f"• ☀️ <b>Morning Brief</b> (Weekdays <code>{esc(morning_time)}</code>): {m_state}\n"
            f"• 🌙 <b>Evening Recap</b> (Weekdays <code>{esc(evening_time)}</code>): {e_state}\n\n"
            "Includes global indices (US / SG / HK / CN), your watchlist movers, and an AI commentary.\n"
            "<i>Toggle below or preview right now 👇</i>"
        )
    m_state = "✅ 已开启" if sub.morning_enabled else "⬜ 未开启"
    e_state = "✅ 已开启" if sub.evening_enabled else "⬜ 未开启"
    return (
        "⏰ <b>定时早晚报订阅中心</b>\n\n"
        f"• ☀️ <b>盘前早报</b>（工作日 <code>{esc(morning_time)}</code>）：{m_state}\n"
        f"• 🌙 <b>盘后晚报</b>（工作日 <code>{esc(evening_time)}</code>）：{e_state}\n\n"
        "内容包含：全球大盘（美股/新加坡/港股/A股）+ 你的自选股涨跌 + AI 简评。\n"
        "<i>点击下方按钮一键开关或立即预览 👇</i>"
    )


def format_alerts(alerts: list[PriceAlert], lang: Lang = "en") -> str:
    en = lang == "en"
    if not alerts:
        return (
            "🔔 <b>Price Alerts</b>\n\n"
            "No active price alerts.\n"
            "Examples:\n"
            "• <code>/alert NVDA &gt; 150</code>\n"
            "• <code>/alert D05.SI &lt; 40</code>\n"
            "• <code>/alert 600519 &gt; 1600</code>"
            if en
            else "🔔 <b>价格预警列表</b>\n\n"
            "当前没有生效中的价格预警。\n"
            "使用示例：\n"
            "• <code>/alert NVDA &gt; 150</code>\n"
            "• <code>/alert D05.SI &lt; 40</code>\n"
            "• <code>/alert 600519 &gt; 1600</code>"
        )

    lines = [
        f"🔔 <b>Active Price Alerts</b> ({len(alerts)})" if en else f"🔔 <b>生效中的价格预警</b>（共 {len(alerts)} 条）",
        "",
    ]
    for a in alerts:
        sym = "≥" if a.direction == "above" else "≤"
        lines.append(
            f"• <code>#{a.id}</code> <b>{esc(a.name)}</b> (<code>{esc(a.code)}</code>)  {sym} <code>{a.target_price:.2f}</code>"
        )
    lines.append(
        "\n<i>Send <code>/alert del ID</code> or tap below to remove.</i>"
        if en
        else "\n<i>发送 <code>/alert del 编号</code> 或点击下方按钮删除预警。</i>"
    )
    return "\n".join(lines)


def markdown_to_telegram_html(text: str) -> str:
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
