"""Application configuration loaded from environment variables or .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = Field(..., description="Telegram Bot API token from @BotFather")
    telegram_proxy: str | None = Field(
        default=None,
        description="Optional proxy URL ONLY for Telegram API, e.g. http://127.0.0.1:7890",
    )

    # LLM (OpenAI-compatible: DeepSeek V3.2/R1, OpenAI GPT-5, Gemini 2.5, Qwen3)
    llm_api_key: str = Field(..., description="API key for the LLM provider")
    llm_base_url: str = Field(
        default="https://api.deepseek.com",
        description="OpenAI-compatible base URL",
    )
    llm_model: str = Field(default="deepseek-chat", description="Model identifier")
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=3000, ge=256, le=16384)

    # Interactive Mini App / WebApp
    webapp_enabled: bool = Field(default=True, description="Run embedded FastAPI interactive dashboard")
    webapp_host: str = Field(default="0.0.0.0")
    webapp_port: int = Field(
        default=8080,
        validation_alias=AliasChoices("WEBAPP_PORT", "PORT"),
    )
    webapp_url: str | None = Field(
        default=None,
        description="Public HTTPS URL for Telegram Mini App button",
    )

    # Scheduled briefings & alerts
    timezone: str = Field(default="Asia/Shanghai")
    morning_brief_time: str = Field(default="09:00")
    evening_brief_time: str = Field(default="15:30")
    alert_poll_seconds: int = Field(default=300, ge=30)

    # Optional Tushare token
    tushare_token: str | None = Field(default=None, description="Optional Tushare Pro token")

    # Storage & cache
    database_path: Path = Field(default=Path("data/stock_bot.db"))
    cache_ttl_seconds: int = Field(default=300, ge=10)
    log_level: str = Field(default="INFO")
