# Telegram A-Share AI Stock Assistant (v2.0)

现代化、全异步的 **A 股智能投研 Telegram 机器人**。支持自然语言多轮对话（Tool-Calling Financial Agent）、内联卡片交互、专业红涨绿跌 K 线图、多指标量化技术诊断、财务体检、舆情抓取与个人自选股管理。

---

## ✨ v2.0 核心特性

- **🤖 Tool-Calling AI 投研助理**：直接发送自然语言（如 *「对比一下贵州茅台和五粮液的财务与近期走势」*），大模型自动并行调用行情、财报、技术指标、新闻工具交叉分析，并保留上下文对话记忆。
- **🎴 现代内联卡片交互（InlineKeyboard）**：发 6 位代码或 `/stock 名称`（支持中文模糊搜索）即出结构化卡片，一键原地切换 **日K / 周K / 月K**、查看 **量化技术诊断 / 财务体检 / 最新舆情 / AI 深度研报** 与 **加入自选**，告别刷屏。
- **📊 专业 A 股 K 线图**：基于 `mplfinance` 绘制红涨绿跌蜡烛图 + `MA5/10/20/60` 均线 + 成交量 + `MACD` 副图，支持中文字体并安全释放图形内存。
- **📐 毫秒级量化技术诊断引擎**：取代低效的在线训练 LSTM，计算 MA、MACD、RSI(14)、布林带、KDJ、ATR、20 日年化波动率及支撑/阻力位，输出 0–100 综合评分与信号明细。
- **⚡ 全异步 + 零门槛数据源**：基于 `AkShare`（免费免 Token）为主数据源，支持可选 `Tushare Pro` 增强；内置异步 TTL 缓存与 `aiosqlite` 本地持久化。
- **🔌 兼容任意 OpenAI 接口模型**：默认适配 DeepSeek（`deepseek-chat`），也可通过 `.env` 一键切换 OpenAI、通义千问等任意 OpenAI 兼容服务。

---

## 🏗 项目结构

```text
src/stock_bot/
├── config.py              # pydantic-settings 环境变量配置
├── models.py              # Pydantic 领域数据模型
├── main.py                # 应用入口与命令菜单注册
├── storage/
│   ├── cache.py           # 异步 TTL 内存缓存
│   └── database.py        # aiosqlite（自选股 & 对话记忆）
├── services/
│   ├── market_data.py     # 统一异步行情/财务/新闻服务（AkShare + 可选 Tushare）
│   ├── technical.py       # 多指标量化技术诊断引擎
│   └── chart.py           # mplfinance 专业 A 股 K 线渲染服务
├── agent/
│   ├── tools.py           # OpenAI Function Calling 工具定义与分发
│   └── financial_agent.py # 多轮工具调用 Agent & 一键深度研报
└── bot/
    ├── formatters.py      # 安全 HTML 卡片渲染与超长消息自动分段
    ├── keyboards.py       # InlineKeyboard 内联按钮构建器
    └── handlers.py        # 命令、内联回调与自然语言路由
```

---

## 🚀 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 `TELEGRAM_BOT_TOKEN`（从 [@BotFather](https://t.me/BotFather) 获取）和 `LLM_API_KEY`（如 DeepSeek API Key）。

### 2. 本地运行（推荐使用 `uv`）

```bash
uv sync --extra dev
uv run stock-bot
```

### 3. Docker 一键部署

```bash
docker compose up -d --build
```

---

## 💬 常用指令与交互示例

| 方式 / 指令 | 说明 |
| --- | --- |
| 直接发 `600519` | 立即打开「贵州茅台」交互式行情卡片 |
| `/stock 茅台` | 中文模糊搜索并选择标的 |
| 直接发自然语言 | 如 *「帮我看看宁德时代最近的技术面和新闻」*、*「今天大盘怎么样」* |
| `/market` | 查看上证、深证、创业板、科创50 大盘概览 |
| `/watch` | 查看与管理我的自选股 |
| `/clear` | 清空当前会话的 AI 对话记忆 |
| `/help` | 查看使用指南 |

---

## 🧪 运行测试与代码检查

```bash
uv run pytest
uv run ruff check src tests
```

---

## ⚠️ 免责声明

本项目仅供学习、研究与信息辅助使用，所有数据、量化技术指标与 AI 生成内容均**不构成任何投资建议**。股市有风险，投资需谨慎。
