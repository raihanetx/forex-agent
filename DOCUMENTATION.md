# Forex LLM Trading Agent — Technical Documentation

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FLASK APP (app.py)                        │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │  Config   │  │   Agent      │  │   Council (Round Table)   │ │
│  │  Manager  │  │   (agent.py) │  │   (council.py)            │ │
│  └──────────┘  └──────────────┘  └───────────────────────────┘ │
│        │              │                      │                   │
│        ▼              ▼                      ▼                   │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │config.json│  │  Kilo API    │  │  Multiple Kilo API calls  │ │
│  │(persisted)│  │  (single)    │  │  (one per agent)          │ │
│  └──────────┘  └──────────────┘  └───────────────────────────┘ │
│                       │                      │                   │
│                       ▼                      ▼                   │
│              ┌──────────────────────────────────┐               │
│              │     PARQUET DATA (EUR/USD M1)     │               │
│              │     ~60,500 candles               │               │
│              └──────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### config.py — Configuration Manager

- Loads/saves `config.json`
- Default values for all settings
- `fetch_free_models()` — queries Kilo Gateway API for available free models
- Handles API key, model selection, window size, council settings

### agent.py — Trading Agent

**Classes:**
- `Trade` — represents a single trade (entry, SL, TP, close, result, pips)
- `TradingAgent` — main orchestrator

**TradingAgent workflow:**
1. `load_data(filepath)` — reads parquet file into pandas DataFrame
2. `process_candle()` — processes one candle at a time:
   - Checks if active trade gets closed (SL/TP hit)
   - If no active trade → asks LLM for decision
   - In Round Table mode → delegates to `council.decide()`
   - In Single mode → calls LLM directly
3. `build_prompt()` — creates the text prompt with candle data
4. `call_llm()` — makes HTTP request to Kilo Gateway API
5. `parse_decision()` — extracts BUY/SELL/HOLD + prices from LLM response
6. `run_backtest()` — loops through all candles
7. `get_stats()` — calculates win rate, pips, profit factor

**Trade tracking:**
- Only ONE trade active at a time
- Each candle checks if high/low hits SL or TP
- If SL hit first → LOSS, if TP hit first → WIN
- All trades logged with timestamps and outcomes

### council.py — Round Table Meeting

**Flow:**
1. **Opening Statements** — each agent independently analyzes the same data
2. **Discussion** — agents see each other's opinions and debate
3. **Final Vote** — must be 100% unanimous

**Key design decisions:**
- ALL agents receive IDENTICAL data (same candle table)
- ALL agents receive the SAME system prompt
- The ONLY difference is which LLM model each agent uses
- Different models naturally interpret data differently — that's the diversity
- No artificial "personalities" — just different AIs looking at the same data

**Unanimous consensus:**
- If ALL agents agree → that's the decision
- If even ONE disagrees → HOLD (no trade)
- This prevents false signals — if models can't agree, the market is unclear

### app.py — Flask Web Server

- Serves the dashboard HTML
- REST API for config, model fetching, data management, agent control
- Background threading for backtest execution
- Log buffer (last 500 messages) for live polling

### dashboard.html — Frontend

Single-file frontend (HTML + CSS + JS):
- **Left sidebar** — settings (collapsible)
- **Center** — live meeting feed (auto-scrolling)
- **Right** — trade history and vote summary
- Polls `/api/status` every second for live updates

## Data Pipeline

```
HuggingFace Dataset
       │
       ▼ (auto-download on first run)
Parquet Files (data/)
       │
       ▼ (pandas read_parquet)
DataFrame (sorted by timestamp)
       │
       ▼ (sliding window of 20 candles)
Text Table (formatted OHLCV)
       │
       ▼ (sent as prompt to LLM)
LLM Response (DECISION + ENTRY + SL + TP + REASON)
       │
       ▼ (parsed and tracked)
Trade Object (open → monitor → close → log)
```

## LLM Integration

**Provider:** Kilo Gateway (kilo.ai)
**Format:** OpenAI-compatible API
**Endpoint:** `POST /chat/completions`

**Request:**
```json
{
  "model": "kilo-auto/free",
  "messages": [
    {"role": "system", "content": "You are a professional Forex trader..."},
    {"role": "user", "content": "Last 20 candles:\n[OHLCV table]\n\nBUY/SELL/HOLD?"}
  ],
  "max_tokens": 800,
  "temperature": 0.3
}
```

**Response parsing:**
- Looks for `DECISION:`, `ENTRY:`, `STOP_LOSS:`, `TAKE_PROFIT:`, `REASON:` lines
- Fallback: scans first 200 chars for BUY/SELL keywords
- Handles models that put reasoning in `reasoning` field vs `content` field

## Performance Metrics

| Metric | Description |
|---|---|
| Total Trades | Number of completed trades |
| Wins / Losses | Trades that hit TP vs SL |
| Win Rate | Wins / Total × 100 |
| Total Pips | Sum of all trade pips |
| Avg Pips | Total Pips / Total Trades |
| Best Trade | Highest pips in a single trade |
| Worst Trade | Lowest pips in a single trade |

## Extending the Project

### Add a new data source:
1. Place `.parquet` file in `data/` directory
2. Must have columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`
3. Select it from the dashboard dropdown

### Use a different LLM provider:
1. Change `base_url` in config to your OpenAI-compatible endpoint
2. Change `model` to your model name
3. Ensure the API follows OpenAI chat completions format

### Add more agents to Round Table:
1. Edit `AGENTS_META` in `dashboard.html` (add agent_6, agent_7, etc.)
2. Update `numAgents` select options
3. The council code automatically handles any number of agents
