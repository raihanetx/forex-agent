# Forex LLM Trading Agent — Project Documentation

## 1. Project Overview

**Goal:** Build a Python-based AI trading agent that reads historical Forex candle data and predicts BUY / SELL / HOLD decisions using an LLM as the decision-making brain.

**No ML training. No indicators. No custom models.** The LLM reads raw price data (like a human reading a chart) and makes trading calls.

---

## 2. Why LLM Instead of Traditional Indicators?

| Traditional Indicators | LLM Approach |
|---|---|
| RSI, MACD, SMA — formula-based, lagging | Reads raw candle patterns like a human trader |
| Needs parameter tuning (period, multiplier, etc.) | No parameters to tune |
| Can't adapt to context | Understands context (trend, momentum, rejection) |
| Generates signals mechanically | Gives reasoning with every decision |
| Can't explain "why" beyond the formula | Explains reasoning in natural language |

**Bottom line:** Indicators are math. Markets are psychology. LLM reads price action the way a skilled trader does — pattern, context, decision.

---

## 3. Data

| Field | Value |
|---|---|
| **Source** | HuggingFace: `Raihan1234/forex-1min-ohlc-multi-tf` |
| **Currency Pair** | EUR/USD |
| **Timeframe** | M1 (1-minute candles) |
| **Period** | February 2026 + March 2026 |
| **Files** | `EURUSD_M1_February_2026.parquet` (28,704 candles) |
| | `EURUSD_M1_March_2026.parquet` (31,796 candles) |
| **Columns** | timestamp, open, high, low, close, volume |
| **Total Candles** | 60,500 |

---

## 4. Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    TRADING AGENT LOOP                        │
│                                                              │
│  ┌──────────┐     ┌──────────────┐     ┌─────────────────┐  │
│  │  PARQUET  │────▶│  PYTHON      │────▶│  LLM (Kilo      │  │
│  │  FILE     │     │  CONVERTER   │     │  Gateway)       │  │
│  └──────────┘     └──────────────┘     └─────────────────┘  │
│                         │                     │              │
│                         │                     ▼              │
│                         │            ┌─────────────────┐    │
│                         │            │  BUY / SELL /    │    │
│                         │            │  HOLD + REASON   │    │
│                         │            └─────────────────┘    │
│                         │                     │              │
│                         ▼                     ▼              │
│                  ┌──────────────────────────────────┐       │
│                  │         LOG & TRACK               │       │
│                  │  - Decision                       │       │
│                  │  - Entry price                    │       │
│                  │  - Stop Loss / Take Profit        │       │
│                  │  - Actual outcome (win/loss)      │       │
│                  └──────────────────────────────────┘       │
│                              │                              │
│                              ▼                              │
│                  ┌──────────────────────────────────┐       │
│                  │     PERFORMANCE REPORT            │       │
│                  │  - Total trades                   │       │
│                  │  - Win rate                       │       │
│                  │  - Profit/Loss                    │       │
│                  └──────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### Step-by-Step:

1. **Load** — Python reads `.parquet` file
2. **Window** — Takes last N candles (default: 20)
3. **Format** — Converts candle data to clean text table
4. **Prompt** — Sends text table to LLM with trading question
5. **Decision** — LLM returns BUY/SELL/HOLD + entry/SL/TP + reason
6. **Log** — Python saves the decision with timestamp and price
7. **Evaluate** — After processing all candles, calculate win/loss stats
8. **Repeat** — Slide window to next candle, go to Step 3

---

## 5. LLM Brain — Kilo Gateway

| Field | Value |
|---|---|
| **Provider** | Kilo Gateway (kilo.ai) |
| **Base URL** | `https://api.kilo.ai/api/gateway` |
| **Endpoint** | `POST /chat/completions` |
| **API Format** | OpenAI-compatible |
| **Auth** | `Bearer <API_KEY>` |
| **Model (recommended)** | `kilo-auto/balanced` (good quality, low cost) |
| **Role** | Trading decision maker (the "brain") |
| **Input** | Text table of last 20 OHLCV candles |
| **Output** | BUY/SELL/HOLD + entry price + SL + TP + reasoning |

### API Call Format:

```python
POST https://api.kilo.ai/api/gateway/chat/completions
Headers:
  Authorization: Bearer <token>
  Content-Type: application/json

Body:
{
  "model": "kilo-auto/balanced",
  "messages": [
    {"role": "system", "content": "You are a professional Forex trader..."},
    {"role": "user", "content": "Last 20 candles:\n[OHLCV table]\n\nBUY/SELL/HOLD?"}
  ],
  "max_tokens": 300,
  "temperature": 0.3
}
```

### What the LLM receives (example prompt):

```
You are a professional Forex trader analyzing EUR/USD M1 data.

Last 20 candles:
Time                Open      High      Low       Close     Volume
2026-03-15 10:00    1.16520   1.16580   1.16490   1.16560   145
2026-03-15 10:01    1.16560   1.16610   1.16540   1.16590   167
...

Current price: 1.16480

Based on price action, should I BUY, SELL, or HOLD?
Respond in this exact format:
DECISION: [BUY/SELL/HOLD]
ENTRY: [price]
STOP_LOSS: [price]
TAKE_PROFIT: [price]
REASON: [1-2 sentence explanation]
```

### What the LLM responds:

```
DECISION: SELL
ENTRY: 1.16480
STOP_LOSS: 1.16610
TAKE_PROFIT: 1.16350
REASON: Price rejected 1.166 resistance twice with 
increasing volume on bearish candles. Momentum shifting down.
```

---

## 6. File Structure

```
forex_agent/
├── EURUSD_M1_February_2026.parquet
├── EURUSD_M1_March_2026.parquet
├── main.py                  # Main entry point
├── data_loader.py           # Read parquet, sliding window
├── formatter.py             # Convert candles to LLM-friendly text
├── llm_client.py            # Kilo Gateway API calls
├── trader.py                # Decision parser + trade evaluator
├── logger.py                # Log all trades
├── config.py                # Settings (window size, API config)
└── results/
    └── trade_log.csv        # All decisions + outcomes
```

---

## 7. Success Criteria

| Metric | What It Measures |
|---|---|
| **Win Rate** | % of trades that hit TP before SL |
| **Profit Factor** | Gross profit / Gross loss |
| **Max Drawdown** | Worst losing streak |
| **Decision Quality** | Does the LLM give consistent, logical reasoning? |

---

## 8. Constraints & Rules

- **No indicators** — Pure price action only
- **No ML training** — LLM is the brain, no fine-tuning
- **Offline data** — Using historical parquet files, not live feed
- **M1 timeframe** — 1-minute candles for precision
- **Single pair** — EUR/USD only (expandable later)
- **Reproducible** — Same data + same prompt = same analysis

---

## 9. Next Steps

- [ ] Confirm Kilo Gateway API details (endpoint, model, auth)
- [ ] Build data_loader.py
- [ ] Build formatter.py
- [ ] Build llm_client.py
- [ ] Build main.py (orchestrator)
- [ ] Run on February data
- [ ] Review results
- [ ] Run on March data
- [ ] Final performance report
