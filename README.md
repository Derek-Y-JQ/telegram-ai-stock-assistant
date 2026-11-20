# Telegram Global AI Stock Assistant (v2.5)

现代化、全异步的 **全球股市智能投研 Telegram 机器人**，一站式覆盖 **🇨🇳 A 股 · 🇭🇰 港股 · 🇺🇸 美股**。支持自然语言多轮工具调用（实时展示思考与数据调取进度）、内联卡片交互、**Telegram Mini App 交互式 K 线与自选看板**、多指标量化技术诊断、每日定时早晚报与价格预警。

---

## ✨ v2.5 核心特性

- **🌍 全球三市场统一覆盖（A 股 + 港股 + 美股）**：
  - 支持直接输入 `600519`（A股）、`00700` / `0700.HK`（港股）、`NVDA` / `AAPL`（美股），以及中文别名模糊搜索（`茅台`、`腾讯`、`英伟达`、`特斯拉`等）。
  - 大盘概览同步展示上证/深证/创业板/科创50、恒生/恒生科技、标普500/纳斯达克/道琼斯。
- **🧠 实时进度 + AI 思考流式展示**：
  - 查股/画图/财务/舆情均带即时加载提示并原地更新，彻底告别“卡死感”。
  - 自然语言对话与 AI 深度研报实时展示工具调用步骤与推理/生成进度（兼容 `deepseek-reasoner` 思考链输出）。
- **📱 交互式 K 线与自选看板（Telegram Mini App）**：
  - 内置 FastAPI + TradingView **Lightweight Charts** 暗黑金融看板，支持双指缩放、十字光标、日/周/月 K 线切换、MA5/10/20 与成交量，以及全球大盘与自选股联动。
- **⏰ 定时早晚报 & 🔔 价格预警**：
  - `/brief` 一键开启/关闭工作日盘前早报（09:00）与盘后晚报（15:30），汇总全球大盘 + 个人自选股 + AI 简评。
  - `/alert NVDA > 150` 或 `/alert 600519 < 1400` 设置价格突破/跌破自动推送。
- **☁️ 24/7 云端免电脑部署**：
  - 内置 `Dockerfile`、`railway.json` 与 `/health` 健康检查，3 分钟部署到 Railway / Zeabur 后关掉电脑也能 24 小时在 iPhone 上随时使用，并自动解锁 HTTPS Mini App 交互看板。

---

## 🚀 快速开始

### 方式一：24/7 云端部署（推荐，不用开电脑 + 解锁交互式 Mini App）

1. 打开 [Railway](https://railway.app) 或 [Zeabur](https://zeabur.com)，用 GitHub 登录并导入本仓库。
2. 在 **Variables（环境变量）** 中填入：
   - `TELEGRAM_BOT_TOKEN`：你的 Bot Token
   - `LLM_API_KEY`：你的 DeepSeek / OpenAI / Gemini / Qwen API Key
   - `LLM_BASE_URL` & `LLM_MODEL`（默认 DeepSeek `deepseek-chat`，可按 `.env.example` 自由切换）
3. 为服务生成一个公网 HTTPS 域名（如 `https://your-app.up.railway.app`），把该域名填到环境变量 `WEBAPP_URL` 中并重新部署，即可在 Telegram 卡片中看到 **📱 打开交互式 K 线看板** 按钮！
4. *(可选)* 挂载一个 Volume 到 `/app/data`，持久化保存自选股、预警和订阅记录。

### 方式二：本地运行（推荐使用 `uv`）

```bash
cp .env.example .env
# 编辑 .env 填入 TELEGRAM_BOT_TOKEN 与 LLM_API_KEY（国内环境可设 TELEGRAM_PROXY）
uv sync --extra dev
uv run stock-bot
```

启动后可同时在浏览器打开 `http://127.0.0.1:8080` 体验交互式 K 线看板。

---

## 💬 常用指令与交互示例

| 方式 / 指令 | 说明 |
| --- | --- |
| 直接发 `600519` / `00700` / `NVDA` | 立即打开对应市场交互式行情卡片 |
| `/stock 茅台` 或 `/stock 英伟达` | 中文模糊搜索 A股 / 港股 / 美股 |
| 直接发自然语言 | 如 *「对比一下英伟达和苹果的盈利能力与技术面」* |
| `/market` | 全球大盘概览（A股 + 港股 + 美股） |
| `/watch` | 查看与管理我的自选股 |
| `/brief` | 订阅/预览每日盘前早报与盘后晚报 |
| `/alert NVDA > 150` | 设置价格预警（`/alert list` 查看生效列表） |
| `/clear` | 清空当前会话的 AI 对话记忆 |

---

## 🧪 测试与代码检查

```bash
uv run pytest -v
uv run ruff check src tests
```

---

## ⚠️ 免责声明

本项目仅供学习、研究与信息辅助使用，所有数据、量化技术指标与 AI 生成内容均**不构成任何投资建议**。股市有风险，投资需谨慎。
