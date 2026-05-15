"""
Trading Agent — Core Logic
- Reads parquet data candle by candle
- Sends window of candles to LLM (single agent OR multi-agent council)
- Parses BUY/SELL/HOLD decisions
- Tracks active trade until SL or TP hit
- Logs all trades with outcomes
"""

import pandas as pd
import requests
import json
import os
import time
from datetime import datetime
from council import TradingCouncil


class Trade:
    """Represents a single active or closed trade."""
    
    def __init__(self, trade_id, direction, entry_price, stop_loss, take_profit, 
                 timestamp, candle_index, reason):
        self.id = trade_id
        self.direction = direction  # BUY or SELL
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.open_time = timestamp
        self.open_candle = candle_index
        self.reason = reason
        self.close_time = None
        self.close_price = None
        self.close_candle = None
        self.result = None  # WIN, LOSS
        self.pips = 0
        self.status = "OPEN"
    
    def check_exit(self, current_high, current_low):
        """Check if current candle hits SL or TP."""
        if self.direction == "BUY":
            if current_low <= self.stop_loss:
                self.close_trade(self.stop_loss, "LOSS")
                return True
            if current_high >= self.take_profit:
                self.close_trade(self.take_profit, "WIN")
                return True
        elif self.direction == "SELL":
            if current_high >= self.stop_loss:
                self.close_trade(self.stop_loss, "LOSS")
                return True
            if current_low <= self.take_profit:
                self.close_trade(self.take_profit, "WIN")
                return True
        return False
    
    def close_trade(self, close_price, result):
        self.close_price = close_price
        self.result = result
        self.status = "CLOSED"
        
        if self.direction == "BUY":
            self.pips = (close_price - self.entry_price) * 10000
        else:
            self.pips = (self.entry_price - close_price) * 10000
    
    def to_dict(self):
        return {
            "id": self.id,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "open_time": str(self.open_time),
            "open_candle": self.open_candle,
            "reason": self.reason,
            "close_time": str(self.close_time),
            "close_price": self.close_price,
            "close_candle": self.close_candle,
            "result": self.result,
            "pips": round(self.pips, 1),
            "status": self.status,
        }


class TradingAgent:
    def __init__(self, config):
        self.config = config
        self.df = None
        self.trades = []           # All trades (closed + active)
        self.active_trade = None   # Currently open trade
        self.trade_counter = 0
        self.current_index = 0     # Which candle we're at
        self.is_running = False
        self.is_paused = False
        self.log_callback = None   # Function to call for live logging
        self.speed = 0.5           # Seconds between candles
        self.last_council_result = None  # Store last council decision details
        
        # Multi-agent council mode
        self.use_council = config.get("use_council", False)
        if self.use_council:
            self.council = TradingCouncil(config)
        else:
            self.council = None
    
    def load_data(self, filepath):
        """Load parquet file."""
        self.df = pd.read_parquet(filepath)
        self.df.index = pd.to_datetime(self.df.index)
        self.df.sort_index(inplace=True)
        self.current_index = self.config["window_size"]
        return len(self.df)
    
    def set_log_callback(self, callback):
        """Set function to receive live log updates."""
        self.log_callback = callback
        if self.council:
            self.council.set_log_callback(callback)
    
    def log(self, msg, level="info"):
        """Send log to callback if set."""
        if self.log_callback:
            self.log_callback(msg, level)
        print(f"[{level.upper()}] {msg}")
    
    def build_prompt(self, window_data, current_price):
        """Build the text prompt for the LLM from candle data."""
        
        lines = []
        lines.append("You are a professional Forex trader analyzing EUR/USD M1 (1-minute) price data.")
        lines.append("Analyze the last 20 candles and decide: BUY, SELL, or HOLD.")
        lines.append("")
        lines.append("RULES:")
        lines.append("- Only say BUY if you see clear upward momentum or reversal pattern")
        lines.append("- Only say SELL if you see clear downward momentum or reversal pattern")
        lines.append("- Say HOLD if the market is choppy or unclear")
        lines.append("- Always set realistic Stop Loss and Take Profit levels")
        lines.append("- Risk:Reward ratio should be at least 1:1.5")
        lines.append("")
        lines.append(f"Current price: {current_price}")
        lines.append("")
        lines.append("Last 20 candles (Open, High, Low, Close, Volume):")
        lines.append(f"{'Time':<22} {'Open':<10} {'High':<10} {'Low':<10} {'Close':<10} {'Vol':<8}")
        lines.append("-" * 70)
        
        for idx, row in window_data.iterrows():
            time_str = idx.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"{time_str:<22} {row['open']:<10.5f} {row['high']:<10.5f} "
                f"{row['low']:<10.5f} {row['close']:<10.5f} {row['volume']:<8.1f}"
            )
        
        lines.append("")
        lines.append("CRITICAL: Your FIRST line MUST be exactly one of these:")
        lines.append("DECISION: BUY")
        lines.append("DECISION: SELL")
        lines.append("DECISION: HOLD")
        lines.append("")
        lines.append("If BUY or SELL, you MUST include ENTRY, STOP_LOSS, TAKE_PROFIT on separate lines.")
        lines.append("If HOLD, set ENTRY/STOP_LOSS/TAKE_PROFIT to 0.")
        lines.append("Keep REASON to 1 sentence max. No analysis. No explanation before DECISION line.")
        lines.append("")
        lines.append("Example response:")
        lines.append("DECISION: SELL")
        lines.append("ENTRY: 1.16480")
        lines.append("STOP_LOSS: 1.16610")
        lines.append("TAKE_PROFIT: 1.16350")
        lines.append("REASON: Bearish rejection at resistance with increasing volume.")
        
        return "\n".join(lines)
    
    def call_llm(self, prompt):
        """Call Kilo Gateway API and return parsed response."""
        try:
            resp = requests.post(
                self.config["base_url"],
                headers={
                    "Authorization": f"Bearer {self.config['api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.config["model"],
                    "messages": [
                        {"role": "system", "content": "You are a precise Forex trading analyst. Follow the output format exactly."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": self.config["max_tokens"],
                    "temperature": self.config["temperature"],
                },
                timeout=60,
            )
            
            if resp.status_code != 200:
                self.log(f"API error: {resp.status_code} - {resp.text}", "error")
                return None
            
            data = resp.json()
            choice = data["choices"][0]
            message = choice["message"]
            
            # Get content and reasoning
            content = message.get("content", "") or ""
            reasoning = message.get("reasoning", "") or ""
            
            # Some models put response in reasoning when content is empty
            if not content.strip() and reasoning:
                content = reasoning
            
            return {
                "content": content.strip(),
                "reasoning": reasoning.strip(),
                "model": data.get("model", "unknown"),
                "usage": data.get("usage", {}),
            }
        
        except Exception as e:
            self.log(f"LLM call failed: {e}", "error")
            return None
    
    def parse_decision(self, llm_response):
        """Parse BUY/SELL/HOLD from LLM response text."""
        if not llm_response:
            return None
        
        content = llm_response["content"]
        
        result = {
            "decision": "HOLD",
            "entry": 0,
            "stop_loss": 0,
            "take_profit": 0,
            "reason": "",
            "raw_response": content,
            "reasoning": llm_response.get("reasoning", ""),
            "model": llm_response.get("model", ""),
        }
        
        # Find DECISION line (search through all lines)
        lines = content.split("\n")
        for i, line in enumerate(lines):
            clean = line.strip().upper()
            
            # Match DECISION
            if "DECISION" in clean and ":" in clean:
                val = clean.split(":", 1)[1].strip()
                if "BUY" in val:
                    result["decision"] = "BUY"
                elif "SELL" in val:
                    result["decision"] = "SELL"
                else:
                    result["decision"] = "HOLD"
            
            # Match ENTRY
            if "ENTRY" in clean and ":" in clean:
                try:
                    num_str = clean.split(":", 1)[1].strip()
                    result["entry"] = float(''.join(c for c in num_str if c.isdigit() or c == '.' or c == '-'))
                except:
                    pass
            
            # Match STOP_LOSS or STOP LOSS
            if ("STOP_LOSS" in clean or "STOP LOSS" in clean or "SL" == clean.split(":")[0].strip()) and ":" in clean:
                try:
                    num_str = clean.split(":", 1)[1].strip()
                    result["stop_loss"] = float(''.join(c for c in num_str if c.isdigit() or c == '.' or c == '-'))
                except:
                    pass
            
            # Match TAKE_PROFIT or TAKE PROFIT
            if ("TAKE_PROFIT" in clean or "TAKE PROFIT" in clean or "TP" == clean.split(":")[0].strip()) and ":" in clean:
                try:
                    num_str = clean.split(":", 1)[1].strip()
                    result["take_profit"] = float(''.join(c for c in num_str if c.isdigit() or c == '.' or c == '-'))
                except:
                    pass
            
            # Match REASON
            if "REASON" in clean and ":" in line:
                result["reason"] = line.split(":", 1)[1].strip()
        
        # Fallback: if no DECISION found, try to detect from content
        if result["decision"] == "HOLD" and not any("DECISION" in l.upper() for l in lines):
            upper = content.upper()
            if "SELL" in upper[:200] and "BUY" not in upper[:100]:
                result["decision"] = "SELL"
            elif "BUY" in upper[:200] and "SELL" not in upper[:100]:
                result["decision"] = "BUY"
        
        return result
    
    def process_candle(self):
        """Process one candle. Returns dict with what happened."""
        if self.current_index >= len(self.df):
            return {"status": "END"}
        
        row = self.df.iloc[self.current_index]
        timestamp = self.df.index[self.current_index]
        
        result = {
            "status": "ok",
            "candle_index": self.current_index,
            "timestamp": str(timestamp),
            "price": row["close"],
            "high": row["high"],
            "low": row["low"],
            "trade_action": None,
            "llm_call": None,
        }
        
        # Check if active trade gets closed by this candle
        if self.active_trade and self.active_trade.status == "OPEN":
            self.active_trade.close_time = str(timestamp)
            self.active_trade.close_candle = self.current_index
            closed = self.active_trade.check_exit(row["high"], row["low"])
            
            if closed:
                self.log(
                    f"🔒 TRADE #{self.active_trade.id} CLOSED: {self.active_trade.result} "
                    f"| {self.active_trade.direction} @ {self.active_trade.entry_price} → "
                    f"{self.active_trade.close_price} | {self.active_trade.pips:+.1f} pips",
                    "trade"
                )
                self.active_trade = None
                result["trade_action"] = "CLOSED"
        
        # If no active trade, ask LLM for decision
        if not self.active_trade:
            window_start = max(0, self.current_index - self.config["window_size"])
            window = self.df.iloc[window_start:self.current_index]
            
            self.log(f"📊 Candle #{self.current_index} | {timestamp} | Price: {row['close']:.5f}", "info")
            
            if self.use_council and self.council:
                # ── Multi-Agent Council Mode ──
                consensus = self.council.decide(window, row["close"])
                self.last_council_result = consensus
                decision = consensus
                
                self.log(
                    f"🏛️  Council: {consensus['decision']} | Confidence: {consensus['confidence']} | "
                    f"Votes: {consensus['vote_counts']}",
                    "decision"
                )
                if consensus.get("reason"):
                    self.log(f"📋 Reason: {consensus['reason'][:200]}", "decision")
            else:
                # ── Single Agent Mode ──
                prompt = self.build_prompt(window, row["close"])
                llm_response = self.call_llm(prompt)
                decision = self.parse_decision(llm_response)
                
                if decision:
                    self.log(f"🧠 Model: {decision.get('model', 'unknown')}", "model")
                    if decision.get("reasoning"):
                        self.log(f"💭 Thinking: {decision['reasoning'][:300]}", "thinking")
                    self.log(f"📋 Decision: {decision['decision']} | Reason: {decision['reason']}", "decision")
            
            if decision:
                result["llm_call"] = decision
                
                if decision["decision"] in ["BUY", "SELL"] and decision.get("entry", 0) > 0:
                    self.trade_counter += 1
                    trade = Trade(
                        trade_id=self.trade_counter,
                        direction=decision["decision"],
                        entry_price=decision["entry"],
                        stop_loss=decision["stop_loss"],
                        take_profit=decision["take_profit"],
                        timestamp=timestamp,
                        candle_index=self.current_index,
                        reason=decision.get("reason", ""),
                    )
                    self.active_trade = trade
                    self.trades.append(trade)
                    
                    self.log(
                        f"🚀 TRADE #{trade.id} OPENED: {trade.direction} @ {trade.entry_price} "
                        f"| SL: {trade.stop_loss} | TP: {trade.take_profit}",
                        "trade"
                    )
                    result["trade_action"] = "OPENED"
        
        self.current_index += 1
        return result
    
    def run_backtest(self, max_candles=None):
        """Run through all candles."""
        self.is_running = True
        processed = 0
        
        total = max_candles or (len(self.df) - self.current_index)
        self.log(f"▶ Starting backtest | {total} candles to process | Window: {self.config['window_size']}", "system")
        
        while self.is_running and self.current_index < len(self.df):
            if self.is_paused:
                time.sleep(0.5)
                continue
            
            result = self.process_candle()
            processed += 1
            
            if result.get("status") == "END":
                break
            
            # Check if we've hit max candles
            if max_candles and processed >= max_candles:
                break
            
            # Only sleep if there's no active trade (to speed up backtest)
            if not self.active_trade:
                time.sleep(self.speed)
        
        # Close any remaining trade
        if self.active_trade and self.active_trade.status == "OPEN":
            last_price = self.df.iloc[-1]["close"]
            self.active_trade.close_price = last_price
            self.active_trade.close_time = str(self.df.index[-1])
            if self.active_trade.direction == "BUY":
                self.active_trade.pips = (last_price - self.active_trade.entry_price) * 10000
            else:
                self.active_trade.pips = (self.active_trade.entry_price - last_price) * 10000
            self.active_trade.result = "WIN" if self.active_trade.pips > 0 else "LOSS"
            self.active_trade.status = "CLOSED"
            self.active_trade = None
        
        self.is_running = False
        self.log("⏹ Backtest complete!", "system")
        return self.get_stats()
    
    def get_stats(self):
        """Calculate performance statistics."""
        closed = [t for t in self.trades if t.status == "CLOSED"]
        wins = [t for t in closed if t.result == "WIN"]
        losses = [t for t in closed if t.result == "LOSS"]
        total_pips = sum(t.pips for t in closed)
        
        stats = {
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
            "total_pips": round(total_pips, 1),
            "avg_pips": round(total_pips / len(closed), 1) if closed else 0,
            "best_trade": round(max((t.pips for t in closed), default=0), 1),
            "worst_trade": round(min((t.pips for t in closed), default=0), 1),
            "candles_processed": self.current_index,
            "total_candles": len(self.df),
            "use_council": self.use_council,
        }
        
        if self.use_council and self.last_council_result:
            stats["council_votes"] = self.last_council_result.get("vote_counts", {})
            stats["council_confidence"] = self.last_council_result.get("confidence", "N/A")
        
        return stats
    
    def get_trades_list(self):
        """Return all trades as list of dicts."""
        return [t.to_dict() for t in self.trades]
    
    def save_trades_csv(self, filepath):
        """Save trade log to CSV."""
        if not self.trades:
            return
        records = [t.to_dict() for t in self.trades]
        df = pd.DataFrame(records)
        df.to_csv(filepath, index=False)
        self.log(f"💾 Trades saved: {filepath}", "system")
