"""OpenAI-compatible Tool definitions and async executor for CN/HK/US/SG financial analysis."""

from __future__ import annotations

import json
import logging
from typing import Any

from stock_bot.models import Lang
from stock_bot.services.market_data import MarketDataService
from stock_bot.services.technical import TechnicalAnalyzer

logger = logging.getLogger(__name__)

TOOL_LABELS: dict[Lang, dict[str, str]] = {
    "en": {
        "get_market_overview": "Global Market Overview",
        "search_stock": "Stock Search",
        "get_stock_quote": "Live Quote",
        "get_stock_finance": "Financials",
        "get_stock_news": "Latest News",
        "get_technical_diagnosis": "Technical Diagnosis",
    },
    "zh": {
        "get_market_overview": "全球大盘概览",
        "search_stock": "搜索标的",
        "get_stock_quote": "查询实时行情",
        "get_stock_finance": "获取财务指标",
        "get_stock_news": "抓取最新舆情",
        "get_technical_diagnosis": "量化技术诊断",
    },
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_market_overview",
            "description": "Get latest levels and daily changes of major global indices (US S&P 500/NASDAQ/Dow, Singapore STI, Hong Kong Hang Seng/HSTECH, China SSE/SZSE/ChiNext/STAR 50).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_stock",
            "description": "Search for stocks across US, Singapore (SGX), Hong Kong (HKEX), and China A-Shares by ticker, code, or company name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword, e.g. 'NVDA', 'DBS', 'D05.SI', '00700', '600519', 'Moutai', '腾讯'"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_quote",
            "description": "Get latest price, daily change, OHLCV, market cap, and valuation for a US, SGX, HK, or CN stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Stock symbol or name, e.g. 'AAPL', 'D05.SI', '00700.HK', '600519'"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_finance",
            "description": "Get key financial indicators (EPS, ROE, margins, debt ratio, revenue/earnings growth, PE/PB) for a US, SGX, HK, or CN stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Stock symbol or name"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_news",
            "description": "Get recent news articles for a US, SGX, HK, or CN stock for sentiment and catalyst analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Stock symbol or name"},
                    "limit": {"type": "integer", "description": "Number of articles, default 6", "default": 6},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_technical_diagnosis",
            "description": "Run multi-indicator quantitative technical analysis (MA, MACD, RSI, Bollinger Bands, KDJ, volatility, support/resistance, score) for a US, SGX, HK, or CN stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Stock symbol or name"},
                },
                "required": ["query"],
            },
        },
    },
]


class FinancialToolset:
    """Executes LLM tool calls against MarketDataService and TechnicalAnalyzer."""

    def __init__(self, market_data: MarketDataService) -> None:
        self.market_data = market_data

    async def execute(self, name: str, arguments_json: str, lang: Lang = "en") -> str:
        try:
            args = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError:
            args = {}

        try:
            if name == "get_market_overview":
                indices = await self.market_data.get_market_overview()
                payload: Any = [i.model_dump() for i in indices]
            elif name == "search_stock":
                candidates = await self.market_data.search_stocks(str(args.get("query", "")))
                payload = [c.model_dump() for c in candidates]
            elif name == "get_stock_quote":
                quote = await self.market_data.get_quote(str(args.get("query", "")))
                payload = quote.model_dump()
            elif name == "get_stock_finance":
                finance = await self.market_data.get_finance(str(args.get("query", "")))
                payload = finance.model_dump()
            elif name == "get_stock_news":
                limit = min(max(int(args.get("limit", 6)), 1), 12)
                candidate, news = await self.market_data.get_news(str(args.get("query", "")), limit=limit)
                payload = {
                    "stock": candidate.model_dump(),
                    "news": [n.model_dump() for n in news],
                }
            elif name == "get_technical_diagnosis":
                candidate, df = await self.market_data.get_kline(str(args.get("query", "")), period="daily", days=180)
                report = TechnicalAnalyzer.analyze(candidate.code, candidate.name, df, lang=lang)
                payload = report.model_dump()
            else:
                payload = {"error": f"Unknown tool: {name}"}
        except Exception as exc:
            logger.warning("Tool %s failed with args=%s: %s", name, args, exc)
            payload = {"error": str(exc)}

        return json.dumps(payload, ensure_ascii=False)
