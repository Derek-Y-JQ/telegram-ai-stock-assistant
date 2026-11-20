"""OpenAI-compatible Tool definitions and async executor for A-share financial analysis."""

from __future__ import annotations

import json
import logging
from typing import Any

from stock_bot.services.market_data import MarketDataService
from stock_bot.services.technical import TechnicalAnalyzer

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_market_overview",
            "description": "获取 A 股主要大盘指数（上证指数、深证成指、创业板指、科创50）的最新点位与涨跌幅。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_stock",
            "description": "根据中文名称或代码关键词搜索匹配的 A 股股票候选列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "股票中文名称或代码关键词，如 '茅台'、'宁德时代'、'600519'"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_quote",
            "description": "获取单只 A 股的最新行情、涨跌幅、成交量额、行业与总市值等基础信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "股票代码或中文名称，如 '600519' 或 '贵州茅台'"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_finance",
            "description": "获取单只 A 股最新财报核心财务指标（EPS、ROE、毛利率、净利率、资产负债率、营收/净利同比增速等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "股票代码或中文名称"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_news",
            "description": "获取单只 A 股近期相关新闻资讯，用于舆情与事件驱动分析。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "股票代码或中文名称"},
                    "limit": {"type": "integer", "description": "返回新闻条数，默认 6", "default": 6},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_technical_diagnosis",
            "description": "对单只 A 股进行多指标量化技术面诊断（MA均线、MACD、RSI、布林带、KDJ、波动率、支撑阻力位及综合评分）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "股票代码或中文名称"},
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

    async def execute(self, name: str, arguments_json: str) -> str:
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
                report = TechnicalAnalyzer.analyze(candidate.code, candidate.name, df)
                payload = report.model_dump()
            else:
                payload = {"error": f"Unknown tool: {name}"}
        except Exception as exc:
            logger.warning("Tool %s failed with args=%s: %s", name, args, exc)
            payload = {"error": str(exc)}

        return json.dumps(payload, ensure_ascii=False)
