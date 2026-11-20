"""OpenAI-compatible Tool definitions and async executor for CN/HK/US financial analysis."""

from __future__ import annotations

import json
import logging
from typing import Any

from stock_bot.services.market_data import MarketDataService
from stock_bot.services.technical import TechnicalAnalyzer

logger = logging.getLogger(__name__)

TOOL_LABELS: dict[str, str] = {
    "get_market_overview": "全球大盘概览",
    "search_stock": "搜索标的",
    "get_stock_quote": "查询实时行情",
    "get_stock_finance": "获取财务指标",
    "get_stock_news": "抓取最新舆情",
    "get_technical_diagnosis": "量化技术诊断",
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_market_overview",
            "description": "获取全球核心大盘指数（A股上证/深证/创业板/科创50、港股恒生/恒生科技、美股标普500/纳斯达克/道琼斯）最新点位与涨跌幅。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_stock",
            "description": "根据中文名称、英文代码或数字代码搜索 A 股、港股或美股标的候选列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "关键词，如 '茅台'、'腾讯'、'英伟达'、'600519'、'00700'、'NVDA'"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_quote",
            "description": "获取单只 A 股、港股或美股的最新行情、涨跌幅、成交量额、行业与估值等基础信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "股票代码或名称，如 '600519'、'00700.HK'、'AAPL'、'英伟达'"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_finance",
            "description": "获取单只 A 股、港股或美股的核心财务指标（EPS、ROE、毛利率、净利率、负债率、营收/净利增速、PE/PB 等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "股票代码或名称"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_news",
            "description": "获取单只 A 股、港股或美股的近期相关新闻资讯，用于舆情与事件驱动分析。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "股票代码或名称"},
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
            "description": "对单只 A 股、港股或美股进行多指标量化技术面诊断（MA均线、MACD、RSI、布林带、KDJ、波动率、支撑阻力位及综合评分）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "股票代码或名称"},
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
