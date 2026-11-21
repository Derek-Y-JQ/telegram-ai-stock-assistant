# Telegram AI Global Stock Assistant

[English](#english) | [中文说明](#中文说明)

---

<a id="english"></a>

## 🌍 English

Search "Stockwatcher" in you Telegram and start chatting with the bot.

An async, AI-powered **Telegram Global Stock Research Assistant** covering **🇺🇸 US**, **🇸🇬 Singapore (SGX)**, **🇭🇰 Hong Kong (HKEX)**, and **🇨🇳 China A-Shares**. Built with a streaming Tool-Calling Financial Agent, interactive **Telegram Mini App** candlestick terminal (TradingView Lightweight Charts), quantitative technical diagnosis, scheduled morning/evening briefings, and price alerts.

### ✨ Key Features

- **🌍 4 Global Markets in One Bot (US · SGX · HK · CN)**:
  - Direct ticker lookup: `NVDA` / `AAPL` (US), `D05.SI` / `DBS` (Singapore SGX), `00700` / `0700.HK` (Hong Kong), `600519` (China A-Shares), plus bilingual fuzzy name search.
  - `/market` displays global indices concurrently: S&P 500, NASDAQ, Dow Jones, Straits Times Index (STI), Hang Seng, Hang Seng Tech, SSE Composite, SZSE Component, ChiNext, and STAR 50.
- **🌐 Bilingual (English Default & Chinese)**:
  - Defaults to **English**; switch anytime with `/lang` (`EN` / `中文`). Both UI, Mini App, and LLM/AI responses follow your selected language.
- **🧠 Streaming Tool-Calling Financial Agent**:
  - Ask natural-language questions (e.g. *"Compare DBS and OCBC fundamentals and technicals"*). The agent invokes live quote, financial, news, and technical tools in parallel and streams reasoning & tool progress in real time.
- **📱 Interactive Market Terminal (Telegram Mini App)**:
  - Embedded FastAPI + TradingView **Lightweight Charts** matte-dark terminal with pinch-to-zoom, live crosshair OHLCV readout, `1D / 1W / 1M` switching, toggleable `MA5 / MA10 / MA20`, Global Markets, and synced Watchlist.
- **📐 Quantitative Technical Diagnosis**:
  - Instant multi-indicator analysis (MA5/10/20/60, MACD, RSI-14, Bollinger Bands, KDJ, ATR, 20D annualized volatility, support/resistance, and 0–100 composite score).
- **⏰ Scheduled Briefings & 🔔 Price Alerts**:
  - `/brief` toggles automated weekday morning & evening briefings (global indices + watchlist movers + AI commentary).
  - `/alert NVDA > 150` or `/alert D05.SI < 40` monitors target prices and pushes instant alerts.
- **☁️ 24/7 Cloud Ready**:
  - Single Docker container runs the Bot, APScheduler, and FastAPI Mini App (`GET /health`) with zero-config `railway.json`.

### 🚀 Quick Start

#### Option 1: 24/7 Cloud Deployment (Recommended — Railway / Zeabur)
1. Import this GitHub repository into [Railway](https://railway.app) or [Zeabur](https://zeabur.com).
2. Add environment variables:
   - `TELEGRAM_BOT_TOKEN`: from [@BotFather](https://t.me/BotFather)
   - `LLM_API_KEY`: DeepSeek, OpenAI, Gemini, or Qwen API key (see `.env.example` for `LLM_BASE_URL` & `LLM_MODEL`)
3. Generate a public HTTPS domain on the platform (port `8080`) and set `WEBAPP_URL=https://your-domain` to unlock the interactive Telegram Mini App button.
4. *(Recommended)* Mount a persistent Volume to `/app/data` to keep watchlists, alerts, language preferences, and subscriptions across redeploys.

#### Option 2: Run Locally with `uv`
```bash
cp .env.example .env
# Fill in TELEGRAM_BOT_TOKEN and LLM_API_KEY
uv sync --extra dev
uv run stock-bot
```
Open `http://127.0.0.1:8080` in your browser to preview the interactive terminal locally.

### 💬 Commands

| Command / Input | Description |
| --- | --- |
| `NVDA` / `D05.SI` / `00700` / `600519` | Open interactive stock quote card |
| `/stock <name or ticker>` | Search across US, SGX, HK, and CN markets |
| Any natural-language message | Ask the AI research agent with live tool calling |
| `/market` | Global index overview (US / SG / HK / CN) |
| `/watch` | View & manage watchlist |
| `/brief` | Subscribe/preview daily morning & evening briefings |
| `/alert <ticker> > <price>` | Set price alert (`/alert list` to view active alerts) |
| `/lang` | Switch between English & 中文 (syncs UI + AI) |
| `/clear` | Clear AI conversation memory |

### 🧪 Testing & Linting
```bash
uv run pytest -v
uv run ruff check src tests
```

---

<a id="中文说明"></a>

## 🇨🇳 中文说明

在你的Telegram上搜索“Stockwatcher”即可开始对话。

现代化、全异步的 **全球股市智能投研 Telegram 机器人**，一站式覆盖 **🇺🇸 美股 · 🇸🇬 新加坡 (SGX) · 🇭🇰 港股 · 🇨🇳 A 股**。默认界面与 AI 回复均为英文，支持通过 `/lang` 一键在中英文间无缝切换。

### ✨ 核心亮点

- **🌍 全球四大市场统一覆盖**：直接输入 `NVDA`、`D05.SI`（或 `DBS`/`星展`）、`00700`（或 `腾讯`）、`600519`（或 `茅台`）即可打开交互卡片；`/market` 同步展示美股三大指数、新加坡海峡时报指数（STI）、恒生/恒生科技与 A 股四大指数。
- **🌐 中英文一键切换（默认英文）**：发送 `/lang` 或点击按钮切换，机器人界面、交互式小程序与大模型 AI 研报/对话输出同步切换。
- **🧠 流式思考进度 + Tool-Calling AI 投研**：自然语言提问即可自动并行调用行情、财报、技术指标和新闻工具，实时展示思考与数据调取进度。
- **📱 专业暗黑风交互式 K 线终端（Telegram Mini App）**：内置 FastAPI + TradingView **Lightweight Charts**，支持双指缩放、实时十字光标 OHLCV 读数、`1D/1W/1M` 切换、均线开关、全球大盘与自选股联动。
- **⏰ 定时早晚报 & 🔔 价格预警**：`/brief` 开启工作日盘前早报与盘后晚报；`/alert D05.SI > 45` 设置价格突破/跌破自动推送。
- **☁️ 24/7 云端部署**：单容器同时运行 Bot、定时调度与 Mini App，配合 `Dockerfile` 与 `railway.json` 3 分钟部署到 Railway / Zeabur，关掉电脑也能随时在 iPhone 上使用。

---

## ⚠️ Disclaimer / 免责声明

This project is for educational and informational purposes only. All market data, quantitative indicators, and AI-generated content do **not** constitute financial or investment advice.
本项目仅供学习、研究与信息辅助使用，所有数据、技术指标与 AI 生成内容均**不构成任何投资建议**。
