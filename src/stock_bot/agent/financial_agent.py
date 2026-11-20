"""Async Tool-Calling Financial AI Agent with live thinking & streaming progress callbacks."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from openai import AsyncOpenAI

from stock_bot.agent.tools import TOOL_DEFINITIONS, TOOL_LABELS, FinancialToolset
from stock_bot.config import Settings
from stock_bot.services.market_data import MarketDataService
from stock_bot.services.technical import TechnicalAnalyzer
from stock_bot.storage.database import Database

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], Awaitable[None]]

SYSTEM_PROMPT = """你是一名专业、客观、严谨的全球股市智能投研助理（覆盖 A 股、港股、美股）。

工作原则：
1. 涉及任何具体股票、指数、财报、技术指标或近期新闻时，务必先调用工具获取真实数据，严禁凭记忆编造价格或财务数字。
2. 当用户对比多只股票或询问综合看法时，可并行调用多个工具交叉验证基本面、技术面与舆情面。
3. 回答要结构清晰、重点突出、简洁易读（适合在 Telegram 手机端阅读），避免冗长空话。
4. 禁止使用复杂 Markdown 表格（手机端会错乱），请使用分段标题、项目符号和关键数据加粗/清晰排版。
5. 始终保持客观中立，说明潜在风险，并在涉及投资判断时附上简短的风险提示（仅供参考，不构成投资建议）。"""

DEEP_REPORT_PROMPT = """请基于以下真实采集的股票多维数据（行情 + 财务 + 量化技术指标 + 近期新闻），生成一份结构化、适合 Telegram 阅读的深度投研简报。

输出结构：
1. 核心结论（一句话定调 + 多维景气度概览）
2. 技术面诊断（趋势、关键均线、MACD/RSI/KDJ 共振、支撑与阻力位）
3. 基本面与财务体检（盈利能力、成长性、估值与财务安全边际）
4. 舆情与事件催化（提炼新闻核心利好/利空及情绪倾向）
5. 关注要点与风险提示（客观给出观察窗口与主要风险，附免责声明）

注意：不要使用 Markdown 表格，直接用简洁的列表和分段呈现。"""


def _format_tool_step(name: str, arguments_json: str) -> str:
    label = TOOL_LABELS.get(name, name)
    try:
        args = json.loads(arguments_json) if arguments_json else {}
        q = args.get("query")
        if q:
            return f"{label}({q})"
    except Exception:
        pass
    return label


class FinancialAgent:
    """Multi-turn Tool-Calling Financial Agent with persistent chat memory & live progress."""

    def __init__(
        self,
        settings: Settings,
        market_data: MarketDataService,
        database: Database,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings
        self.market_data = market_data
        self.database = database
        self.toolset = FinancialToolset(market_data)
        self.client = client or AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )

    async def chat(
        self,
        chat_id: int,
        user_message: str,
        max_tool_rounds: int = 6,
        on_progress: ProgressCallback | None = None,
    ) -> str:
        """Handle a natural language user message with autonomous tool calling and live progress."""
        history = await self.database.get_recent_messages(chat_id, limit=8)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_message},
        ]

        final_reply = "抱歉，我暂时没能生成有效回答，请稍后再试。"
        executed_steps: list[str] = []

        for round_idx in range(max_tool_rounds):
            if on_progress:
                if round_idx == 0:
                    await on_progress("🧠 正在理解你的问题并规划数据调取...")
                else:
                    steps_preview = "\n".join(f"✅ {s}" for s in executed_steps[-4:])
                    await on_progress(f"🧠 正在结合已获取数据深度思考...\n\n{steps_preview}")

            response = await self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
            )
            msg = response.choices[0].message

            # Surface reasoning preview if the model returns reasoning_content (e.g. DeepSeek-R1)
            reasoning = getattr(msg, "reasoning_content", None)
            if reasoning and on_progress:
                snippet = str(reasoning).strip().replace("\n", " ")[:180]
                await on_progress(f"💭 AI 思考中：\n{snippet}...")

            if not msg.tool_calls:
                final_reply = (msg.content or "").strip() or final_reply
                break

            step_labels = [_format_tool_step(tc.function.name, tc.function.arguments) for tc in msg.tool_calls]
            if on_progress:
                current_text = "、".join(step_labels)
                done_block = ("\n".join(f"✅ {s}" for s in executed_steps[-4:]) + "\n") if executed_steps else ""
                await on_progress(f"🔧 正在实时调取市场数据：\n{done_block}⏳ {current_text}...")

            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )

            tool_results = await asyncio.gather(
                *(
                    self.toolset.execute(tc.function.name, tc.function.arguments)
                    for tc in msg.tool_calls
                )
            )
            executed_steps.extend(step_labels)

            for tc, result in zip(msg.tool_calls, tool_results, strict=True):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    }
                )

        await self.database.append_message(chat_id, "user", user_message)
        await self.database.append_message(chat_id, "assistant", final_reply)
        return final_reply

    async def generate_deep_report(
        self,
        code_or_name: str,
        on_progress: ProgressCallback | None = None,
    ) -> str:
        """Concurrently gather quote, finance, technicals, and news, then stream an AI research report."""
        candidate = await self.market_data.resolve_stock(code_or_name)
        if on_progress:
            await on_progress(
                f"🔍 正在为 {candidate.name}({candidate.ts_code}) 并行采集多维数据：\n"
                "⏳ 实时行情 · 财务指标 · 量化技术面 · 最新舆情..."
            )

        async def _safe_quote() -> dict[str, Any]:
            try:
                return (await self.market_data.get_quote(candidate.code)).model_dump()
            except Exception as exc:
                return {"error": str(exc)}

        async def _safe_finance() -> dict[str, Any]:
            try:
                return (await self.market_data.get_finance(candidate.code)).model_dump()
            except Exception as exc:
                return {"error": str(exc)}

        async def _safe_technical() -> dict[str, Any]:
            try:
                _, df = await self.market_data.get_kline(candidate.code, period="daily", days=180)
                return TechnicalAnalyzer.analyze(candidate.code, candidate.name, df).model_dump()
            except Exception as exc:
                return {"error": str(exc)}

        async def _safe_news() -> list[dict[str, Any]]:
            try:
                _, items = await self.market_data.get_news(candidate.code, limit=6)
                return [i.model_dump() for i in items]
            except Exception:
                return []

        quote_data, finance_data, tech_data, news_data = await asyncio.gather(
            _safe_quote(),
            _safe_finance(),
            _safe_technical(),
            _safe_news(),
        )

        if on_progress:
            await on_progress(
                f"✅ {candidate.name}({candidate.ts_code}) 四维数据采集完成！\n"
                "🧠 AI 正在深度推理并撰写研报..."
            )

        context_payload = {
            "stock": candidate.model_dump(),
            "quote": quote_data,
            "finance": finance_data,
            "technical": tech_data,
            "news": news_data,
        }

        return await self._stream_completion(
            messages=[
                {"role": "system", "content": DEEP_REPORT_PROMPT},
                {"role": "user", "content": json.dumps(context_payload, ensure_ascii=False)},
            ],
            on_progress=on_progress,
        )

    async def summarize_briefing(self, kind: str, payload: dict[str, Any]) -> str:
        """Generate a concise 3-4 sentence AI commentary for morning/evening briefings."""
        prompt = (
            "你是一名专业股市早晚报主编。请根据以下全球大盘与用户自选股数据，"
            f"写一段简短精炼的{'盘前早报前瞻' if kind == 'morning' else '盘后复盘总结'}（150-220字以内），"
            "重点提炼市场情绪、异动自选股与今日关注点，不要使用 Markdown 表格。"
        )
        response = await self.client.chat.completions.create(
            model=self.settings.llm_model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        return (response.choices[0].message.content or "").strip()

    async def _stream_completion(
        self,
        messages: list[dict[str, Any]],
        on_progress: ProgressCallback | None = None,
    ) -> str:
        """Stream LLM response and push throttled thinking/content previews via on_progress."""
        try:
            stream = await self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
                stream=True,
            )
            reasoning_parts: list[str] = []
            content_parts: list[str] = []
            last_push = 0.0

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                r_piece = getattr(delta, "reasoning_content", None)
                c_piece = getattr(delta, "content", None)
                if r_piece:
                    reasoning_parts.append(str(r_piece))
                if c_piece:
                    content_parts.append(str(c_piece))

                now = time.monotonic()
                if on_progress and (now - last_push >= 1.0):
                    last_push = now
                    if content_parts:
                        preview = "".join(content_parts)
                        if len(preview) > 3200:
                            preview = preview[:3200] + "\n\n✍️ 持续生成中..."
                        else:
                            preview = preview + "\n\n✍️ 持续生成中..."
                        await on_progress(preview)
                    elif reasoning_parts:
                        r_preview = "".join(reasoning_parts).strip()[-280:]
                        await on_progress(f"💭 AI 思考过程：\n...{r_preview}")

            return "".join(content_parts).strip()
        except Exception as exc:
            logger.debug("Streaming fallback to non-streaming completion: %s", exc)
            response = await self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
            )
            return (response.choices[0].message.content or "").strip()
