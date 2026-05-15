---
title: Forex LLM Trading Agent
emoji: ⚡
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: true
license: mit
---

# ⚡ Forex LLM Trading Agent

LLM-powered Forex trading agent that reads EUR/USD M1 candle data and predicts BUY/SELL/HOLD decisions using Kilo Gateway.

## Features

- 📊 Real-time candle-by-candle analysis
- 🧠 LLM thinking display (see what the AI is reasoning)
- 📈 Trade tracking (one trade at a time, tracked until SL/TP)
- 📋 Full trade history with WIN/LOSS + pips
- 🎯 Win rate, profit factor, total pips stats
- ⚙️ Model selection (auto-detects free models)
- 💾 Export trade log to CSV

## Tech Stack

- Python + Flask
- Kilo Gateway (OpenAI-compatible LLM API)
- Pandas + Parquet data
- EUR/USD M1 data (Feb-March 2026)
