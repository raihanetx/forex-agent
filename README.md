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

LLM-powered Forex trading agent that reads EUR/USD M1 candle data and predicts BUY/SELL/HOLD decisions using LLM models via Kilo Gateway.

## What Is This?

A Python/Flask web app that uses **LLMs as trading brains**. No indicators (RSI, MACD), no ML training — the LLM reads raw candle price data like a human trader reading a chart, and makes trading calls.

Two modes:
- **Single Mode** — one LLM analyzes candles and decides BUY/SELL/HOLD
- **Round Table Mode** — multiple LLM agents (you pick which models) analyze the same data, debate, and must reach **unanimous agreement** before taking a trade

## Quick Start

### 1. Get a Kilo Gateway API Key

Go to [kilo.ai](https://kilo.ai) and create a free account. Get your API key from the dashboard.

### 2. Clone & Install

```bash
git clone https://github.com/raihanetx/forex-agent.git
cd forex-agent
pip install -r requirements.txt
```

### 3. Run

```bash
python app.py
```

Open `http://localhost:7860` in your browser.

### 4. Configure

1. Paste your Kilo Gateway API key → click **Save & Fetch Models**
2. Select a data file (EURUSD M1 Feb-March 2026)
3. Choose Single or Round Table mode
4. Click **▶ Start**

## How Single Mode Works

```
Candle Data → LLM → BUY/SELL/HOLD + Entry/SL/TP → Track Trade → Repeat
```

1. Reads 20 candles at a time (sliding window)
2. Sends them to the LLM with a trading prompt
3. LLM responds with DECISION + ENTRY + STOP_LOSS + TAKE_PROFIT + REASON
4. If BUY/SELL → opens a trade, monitors until SL or TP is hit
5. Logs everything, calculates win rate, pips, profit factor

## How Round Table Mode Works

```
┌─────────────────────────────────────────────────┐
│  You pick: 3 agents                             │
│  Agent 1 → gpt-4o-mini                          │
│  Agent 2 → gemini-2.0-flash                     │
│  Agent 3 → kilo-auto/free                       │
│                                                  │
│  ALL THREE get:                                  │
│    ✅ Same candle data                           │
│    ✅ Same system prompt                         │
│    ✅ Same question                              │
│    ❌ Different model (the ONLY difference)      │
│                                                  │
│  Phase 1: Each gives their independent opinion   │
│  Phase 2: They see each other's opinions         │
│           and discuss / debate                   │
│  Phase 3: Must ALL agree → trade                 │
│           Even 1 disagrees → no trade            │
└─────────────────────────────────────────────────┘
```

### Why Unanimous?

If 3 different AI models — trained differently, reasoning differently — all agree on a trade, that's a stronger signal than any single model. If they can't agree, the market is unclear, so we don't trade.

### The Debate

After opening statements, agents see what others said and discuss:
- If you changed your mind based on someone else's reasoning → say so
- If you disagree → argue your case with specific evidence from the data
- Both sides defend their position (not just the minority)

## Dashboard

```
┌────────────┬──────────────────────────────────┬──────────┐
│            │                                  │          │
│  SETTINGS  │         MEETING FEED             │ TRADES   │
│            │                                  │          │
│ API Key    │  Candle #450 | Price: 1.16480    │ Latest   │
│ Data File  │                                  │ Votes    │
│ Model      │  Phase 1: Opening Statements     │          │
│ Round Table│    Agent 1: SELL because...      │ Active   │
│  3 agents  │    Agent 2: BUY because...       │ Trade    │
│  1 round   │    Agent 3: SELL because...      │          │
│            │                                  │ History  │
│ Agent 1 [] │  Phase 2: Discussion             │          │
│ Agent 2 [] │    Agent 2 changed mind...       │          │
│ Agent 3 [] │    Agent 3 sticks with...        │          │
│            │                                  │          │
│ [▶] [⏸] [⏹]│  Phase 3: UNANIMOUS SELL ✅      │          │
│            │                                  │          │
└────────────┴──────────────────────────────────┴──────────┘
```

- **Left sidebar** — all settings (collapsible with ◀/▶ button)
- **Center** — live feed showing the roundtable meeting in real-time
- **Right** — trade history and vote summary

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.12 + Flask |
| Data | Pandas + PyArrow (Parquet files) |
| LLM API | Kilo Gateway (OpenAI-compatible) |
| Data Source | HuggingFace: `Raihan1234/forex-agent-data` |
| Frontend | Vanilla HTML/CSS/JS (no framework) |
| Deployment | Docker (HuggingFace Spaces) |

## Project Structure

```
forex-agent/
├── app.py              # Flask web server + API routes
├── agent.py            # Trading agent core logic
│                        #   - Loads parquet data
│                        #   - Sliding window over candles
│                        #   - Calls LLM (single or council)
│                        #   - Parses BUY/SELL/HOLD decisions
│                        #   - Tracks trades (entry/SL/TP)
│                        #   - Calculates win/loss stats
├── council.py          # Round Table meeting logic
│                        #   - All agents get same data + prompt
│                        #   - Phase 1: Opening statements
│                        #   - Phase 2: Discussion/debate
│                        #   - Phase 3: Unanimous consensus
├── config.py           # Configuration manager
│                        #   - API key, model, window size
│                        #   - Agent selection + models
│                        #   - Persists to config.json
├── templates/
│   └── dashboard.html  # Web dashboard (all-in-one)
├── data/               # Parquet data files (auto-downloaded)
│   ├── EURUSD_M1_February_2026.parquet
│   └── EURUSD_M1_March_2026.parquet
├── results/            # Exported trade logs (CSV)
├── Dockerfile          # Docker config for HF Spaces
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

## Configuration

All settings are saved in `config.json` (auto-created):

| Setting | Default | Description |
|---|---|---|
| `api_key` | `""` | Kilo Gateway API key |
| `model` | `kilo-auto/free` | Default model for single mode |
| `base_url` | `https://api.kilo.ai/api/gateway/chat/completions` | API endpoint |
| `window_size` | `20` | Number of candles to show the LLM |
| `temperature` | `0.3` | LLM temperature (lower = more consistent) |
| `max_tokens` | `800` | Max tokens per LLM response |
| `use_council` | `false` | Enable Round Table mode |
| `num_agents` | `3` | Number of agents in Round Table |
| `debate_rounds` | `1` | How many rounds of discussion |
| `selected_agents` | `[]` | Which agents participate |
| `agent_models` | `{}` | Model assigned to each agent |

## Data

- **Source:** [HuggingFace Dataset](https://huggingface.co/datasets/Raihan1234/forex-agent-data)
- **Pair:** EUR/USD
- **Timeframe:** M1 (1-minute candles)
- **Period:** February 2026 + March 2026
- **Total:** ~60,500 candles
- **Columns:** timestamp, open, high, low, close, volume

Data is auto-downloaded from HuggingFace on first run.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/api/config` | Get current config |
| POST | `/api/config` | Update config |
| POST | `/api/models` | Fetch free models from Kilo |
| GET | `/api/data/files` | List available parquet files |
| POST | `/api/data/download` | Re-download data from HF |
| POST | `/api/start` | Start backtest |
| POST | `/api/pause` | Pause backtest |
| POST | `/api/stop` | Stop backtest |
| GET | `/api/status` | Get current status, stats, logs |
| POST | `/api/save` | Export trades to CSV |

## Deployment (HuggingFace Spaces)

This project is configured for Docker deployment on HuggingFace Spaces:

```bash
# Push to HF Space
git remote add space https://huggingface.co/spaces/YOUR_USERNAME/forex-agent
git push space main
```

The `Dockerfile` uses gunicorn on port 7860 (HF Spaces standard).

## License

MIT
