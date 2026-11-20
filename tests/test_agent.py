"""Tests for FinancialAgent tool-calling loop with mocked AsyncOpenAI."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from stock_bot.agent.financial_agent import FinancialAgent
from stock_bot.config import Settings
from stock_bot.models import IndexQuote
from stock_bot.storage.database import Database


async def test_financial_agent_executes_tool_call_and_persists_history(tmp_path: Path) -> None:
    settings = Settings(
        telegram_bot_token="dummy-token",
        llm_api_key="dummy-key",
        database_path=tmp_path / "agent.db",
    )
    db = Database(settings.database_path)
    await db.init()

    market_data = SimpleNamespace(
        get_market_overview=AsyncMock(
            return_value=[
                IndexQuote(
                    code="000001.SH",
                    name="上证指数",
                    close=3350.12,
                    change_pct=0.85,
                    change_amount=28.23,
                    trade_date="2026-11-20",
                )
            ]
        )
    )

    first_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(name="get_market_overview", arguments="{}"),
                        )
                    ],
                )
            )
        ]
    )
    second_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="今日上证指数收于 3350.12 点（+0.85%），整体偏强。",
                    tool_calls=None,
                )
            )
        ]
    )

    mock_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(side_effect=[first_response, second_response])
            )
        )
    )

    agent = FinancialAgent(
        settings=settings,
        market_data=market_data,  # type: ignore[arg-type]
        database=db,
        client=mock_client,  # type: ignore[arg-type]
    )

    reply = await agent.chat(chat_id=42, user_message="今天大盘怎么样？")
    assert "3350.12" in reply
    market_data.get_market_overview.assert_awaited_once()

    history = await db.get_recent_messages(42)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
