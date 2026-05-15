"""
Multi-Agent Trading Council
Multiple AI agents with different trading personalities vote and debate.
- Each agent votes independently (BUY/SELL/HOLD)
- Majority wins → trade executes
- Split vote → agents debate, then re-vote
- No consensus → no trade (safe approach)
"""

import requests
import json
import time


# ─── Agent Personalities ────────────────────────────────────────────

AGENT_PROFILES = [
    {
        "id": "alpha",
        "name": "Alpha — Trend Follower",
        "emoji": "🔺",
        "style": "trend_following",
        "system_prompt": (
            "You are Alpha, a conservative trend-following trader. You only trade WITH the trend. "
            "You look for higher highs, higher lows (uptrend) or lower highs, lower lows (downtrend). "
            "You are patient and wait for confirmation. You hate guessing. "
            "If the trend is unclear, you ALWAYS say HOLD. You set tight stop losses."
        ),
    },
    {
        "id": "beta",
        "name": "Beta — Momentum Hunter",
        "emoji": "⚡",
        "style": "momentum",
        "system_prompt": (
            "You are Beta, an aggressive momentum trader. You look for strong price moves, "
            "big candles, and volume spikes. You ride momentum and exit fast. "
            "You love breakout trades. You don't care about trends — you care about SPEED and FORCE. "
            "If momentum is weak or choppy, you say HOLD. You use wider stops to avoid noise."
        ),
    },
    {
        "id": "gamma",
        "name": "Gamma — Price Action Purist",
        "emoji": "📐",
        "style": "price_action",
        "system_prompt": (
            "You are Gamma, a pure price action trader. You read candlestick patterns: "
            "pin bars, engulfing candles, dojis, inside bars. You ignore volume. "
            "You care about support/resistance levels and rejection. "
            "You are disciplined — no pattern, no trade. You set SL/TP based on recent swing points."
        ),
    },
    {
        "id": "delta",
        "name": "Delta — Volume Analyst",
        "emoji": "📊",
        "style": "volume",
        "system_prompt": (
            "You are Delta, a volume-focused trader. You believe volume leads price. "
            "High volume on green candles = buyers in control. High volume on red = sellers. "
            "Low volume moves are fake-outs. You only trade when volume CONFIRMS the move. "
            "If volume is inconsistent with price, you say HOLD."
        ),
    },
    {
        "id": "epsilon",
        "name": "Epsilon — Contrarian",
        "emoji": "🔄",
        "style": "contrarian",
        "system_prompt": (
            "You are Epsilon, a contrarian trader. You look for exhaustion and reversal signals. "
            "When everyone is buying, you look to sell. When everyone is selling, you look to buy. "
            "You watch for long wicks, failed breakouts, and divergence. "
            "You are skeptical of strong moves — they often reverse. Set wide TP, tight SL."
        ),
    },
]


# ─── Debate Prompt ──────────────────────────────────────────────────

DEBATE_PROMPT_TEMPLATE = """You are {name}, debating with other traders about EUR/USD.

THE DATA:
Current price: {price}
Last 20 candles:
{candle_table}

YOUR INITIAL VOTE: {my_vote}
YOUR REASONING: {my_reason}

OTHER AGENTS' VOTES:
{other_votes}

YOUR TASK:
1. Defend your position with 2-3 strong arguments
2. Point out flaws in opposing views
3. Be open to changing your mind if convinced
4. If you change your vote, say "REVISED_VOTE: [BUY/SELL/HOLD]"
5. If you stick to your vote, say "STICK_VOTE: [BUY/SELL/HOLD]"

Be direct. No fluff. Argue like a trader, not a professor."""


CONSENSUS_PROMPT = """You are a neutral moderator. Here are the final votes from {num_agents} trading agents:

{votes_summary}

RULES:
- If 3+ agents agree on BUY or SELL → CONSENSUS: [direction]
- If 3+ agents say HOLD → CONSENSUS: HOLD
- If votes are split (2-2-1 or similar) → CONSENSUS: HOLD (no trade)
- If 2 agree on direction but others say HOLD → CONSENSUS: [direction] (weak)

Respond with EXACTLY:
CONSENSUS: [BUY/SELL/HOLD]
CONFIDENCE: [HIGH/MEDIUM/LOW]
REASON: [1 sentence]"""


# ─── Council Class ──────────────────────────────────────────────────

class TradingCouncil:
    """Multi-agent voting and debate system."""
    
    def __init__(self, config):
        self.config = config
        self.agents = AGENT_PROFILES[:config.get("num_agents", 3)]
        self.debate_rounds = config.get("debate_rounds", 1)
        self.consensus_threshold = config.get("consensus_threshold", 0.6)  # 60% agreement needed
        self.log_callback = None
        self.last_debate = None  # Store last debate transcript
    
    def set_log_callback(self, callback):
        self.log_callback = callback
    
    def log(self, msg, level="info"):
        if self.log_callback:
            self.log_callback(msg, level)
        print(f"[{level.upper()}] {msg}")
    
    def build_candle_table(self, window_data, current_price):
        """Build candle text table for prompts."""
        lines = []
        lines.append(f"Current price: {current_price}")
        lines.append("")
        lines.append(f"{'Time':<22} {'Open':<10} {'High':<10} {'Low':<10} {'Close':<10} {'Vol':<8}")
        lines.append("-" * 70)
        
        for idx, row in window_data.iterrows():
            time_str = idx.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"{time_str:<22} {row['open']:<10.5f} {row['high']:<10.5f} "
                f"{row['low']:<10.5f} {row['close']:<10.5f} {row['volume']:<8.1f}"
            )
        
        return "\n".join(lines)
    
    def build_vote_prompt(self, agent, window_data, current_price):
        """Build individual vote prompt for an agent."""
        candle_table = self.build_candle_table(window_data, current_price)
        
        lines = []
        lines.append(agent["system_prompt"])
        lines.append("")
        lines.append("RULES:")
        lines.append("- Only say BUY if you see clear setup for your trading style")
        lines.append("- Only say SELL if you see clear setup for your trading style")
        lines.append("- Say HOLD if conditions don't match your criteria")
        lines.append("- Risk:Reward ratio must be at least 1:1.5")
        lines.append("")
        lines.append(f"Current price: {current_price}")
        lines.append("")
        lines.append("Last 20 candles (Open, High, Low, Close, Volume):")
        lines.append(candle_table)
        lines.append("")
        lines.append("CRITICAL: Your FIRST line MUST be exactly one of these:")
        lines.append("DECISION: BUY")
        lines.append("DECISION: SELL")
        lines.append("DECISION: HOLD")
        lines.append("")
        lines.append("If BUY or SELL, include ENTRY, STOP_LOSS, TAKE_PROFIT on separate lines.")
        lines.append("If HOLD, set ENTRY/STOP_LOSS/TAKE_PROFIT to 0.")
        lines.append("Keep REASON to 1 sentence max.")
        lines.append("")
        lines.append("Example:")
        lines.append("DECISION: SELL")
        lines.append("ENTRY: 1.16480")
        lines.append("STOP_LOSS: 1.16610")
        lines.append("TAKE_PROFIT: 1.16350")
        lines.append("REASON: Bearish rejection at resistance.")
        
        return "\n".join(lines)
    
    def call_llm(self, system_prompt, user_prompt, max_tokens=300):
        """Call LLM API."""
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
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": self.config.get("temperature", 0.3),
                },
                timeout=60,
            )
            
            if resp.status_code != 200:
                self.log(f"API error: {resp.status_code}", "error")
                return None
            
            data = resp.json()
            message = data["choices"][0]["message"]
            content = message.get("content", "") or ""
            reasoning = message.get("reasoning", "") or ""
            
            if not content.strip() and reasoning:
                content = reasoning
            
            return {"content": content.strip(), "reasoning": reasoning.strip()}
        
        except Exception as e:
            self.log(f"LLM call failed: {e}", "error")
            return None
    
    def parse_vote(self, llm_response):
        """Parse a single agent's vote from LLM response."""
        if not llm_response:
            return {"decision": "HOLD", "entry": 0, "stop_loss": 0, "take_profit": 0, "reason": "No response", "raw": ""}
        
        content = llm_response["content"]
        lines = content.split("\n")
        
        result = {
            "decision": "HOLD",
            "entry": 0,
            "stop_loss": 0,
            "take_profit": 0,
            "reason": "",
            "raw": content,
            "reasoning": llm_response.get("reasoning", ""),
        }
        
        for line in lines:
            clean = line.strip().upper()
            
            if "DECISION" in clean and ":" in clean:
                val = clean.split(":", 1)[1].strip()
                if "BUY" in val:
                    result["decision"] = "BUY"
                elif "SELL" in val:
                    result["decision"] = "SELL"
                else:
                    result["decision"] = "HOLD"
            
            if "ENTRY" in clean and ":" in clean:
                try:
                    result["entry"] = float(''.join(c for c in clean.split(":", 1)[1] if c.isdigit() or c == '.' or c == '-'))
                except:
                    pass
            
            if ("STOP_LOSS" in clean or "STOP LOSS" in clean) and ":" in clean:
                try:
                    result["stop_loss"] = float(''.join(c for c in clean.split(":", 1)[1] if c.isdigit() or c == '.' or c == '-'))
                except:
                    pass
            
            if ("TAKE_PROFIT" in clean or "TAKE PROFIT" in clean) and ":" in clean:
                try:
                    result["take_profit"] = float(''.join(c for c in clean.split(":", 1)[1] if c.isdigit() or c == '.' or c == '-'))
                except:
                    pass
            
            if "REASON" in clean and ":" in line:
                result["reason"] = line.split(":", 1)[1].strip()
        
        # Fallback detection
        if result["decision"] == "HOLD" and not any("DECISION" in l.upper() for l in lines):
            upper = content.upper()
            if "SELL" in upper[:200] and "BUY" not in upper[:100]:
                result["decision"] = "SELL"
            elif "BUY" in upper[:200] and "SELL" not in upper[:100]:
                result["decision"] = "BUY"
        
        return result
    
    def collect_votes(self, window_data, current_price):
        """All agents vote independently. Returns list of (agent, vote) tuples."""
        votes = []
        
        for agent in self.agents:
            self.log(f"  {agent['emoji']} {agent['name']} voting...", "agent_vote")
            
            prompt = self.build_vote_prompt(agent, window_data, current_price)
            response = self.call_llm(agent["system_prompt"], prompt)
            vote = self.parse_vote(response)
            vote["agent_id"] = agent["id"]
            vote["agent_name"] = agent["name"]
            vote["agent_emoji"] = agent["emoji"]
            
            votes.append((agent, vote))
            
            self.log(
                f"  {agent['emoji']} {agent['id'].upper()}: {vote['decision']} — {vote['reason'][:80]}",
                "agent_vote"
            )
        
        return votes
    
    def tally_votes(self, votes):
        """Count votes. Returns dict with counts and majority info."""
        counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
        for agent, vote in votes:
            counts[vote["decision"]] += 1
        
        total = len(votes)
        majority_dir = max(counts, key=counts.get)
        majority_count = counts[majority_dir]
        
        return {
            "counts": counts,
            "total": total,
            "majority_dir": majority_dir,
            "majority_count": majority_count,
            "majority_pct": round(majority_count / total * 100),
            "is_consensus": majority_count > total / 2,
            "is_unanimous": majority_count == total,
            "is_split": max(counts.values()) <= total / 2,
        }
    
    def run_debate(self, votes, window_data, current_price):
        """Agents debate their positions. Returns revised votes."""
        candle_table = self.build_candle_table(window_data, current_price)
        
        debate_log = []
        debate_log.append("=" * 60)
        debate_log.append("🗣️  DEBATE ROUND — Agents arguing positions...")
        debate_log.append("=" * 60)
        
        revised_votes = []
        
        for agent, vote in votes:
            # Build "other votes" summary
            other_lines = []
            for other_agent, other_vote in votes:
                if other_agent["id"] != agent["id"]:
                    other_lines.append(
                        f"- {other_agent['emoji']} {other_agent['id'].upper()}: "
                        f"{other_vote['decision']} — {other_vote['reason'][:80]}"
                    )
            
            debate_prompt = DEBATE_PROMPT_TEMPLATE.format(
                name=agent["name"],
                price=current_price,
                candle_table=candle_table,
                my_vote=vote["decision"],
                my_reason=vote["reason"],
                other_votes="\n".join(other_lines),
            )
            
            self.log(f"  {agent['emoji']} {agent['id'].upper()} debating...", "debate")
            
            response = self.call_llm(agent["system_prompt"], debate_prompt, max_tokens=400)
            
            if response:
                content = response["content"]
                debate_log.append(f"\n{agent['emoji']} {agent['name']}:")
                debate_log.append(content[:300])
                
                # Check for revised vote
                revised = vote.copy()
                for line in content.split("\n"):
                    upper = line.strip().upper()
                    if "REVISED_VOTE" in upper and ":" in upper:
                        val = upper.split(":", 1)[1].strip()
                        if "BUY" in val:
                            revised["decision"] = "BUY"
                        elif "SELL" in val:
                            revised["decision"] = "SELL"
                        else:
                            revised["decision"] = "HOLD"
                        self.log(f"  {agent['emoji']} {agent['id'].upper()} REVISED → {revised['decision']}", "debate")
                        break
                    elif "STICK_VOTE" in upper and ":" in upper:
                        val = upper.split(":", 1)[1].strip()
                        if "BUY" in val:
                            revised["decision"] = "BUY"
                        elif "SELL" in val:
                            revised["decision"] = "SELL"
                        else:
                            revised["decision"] = "HOLD"
                        break
                
                revised_votes.append((agent, revised))
            else:
                revised_votes.append((agent, vote))
        
        self.last_debate = "\n".join(debate_log)
        return revised_votes
    
    def get_consensus(self, votes):
        """
        Determine final consensus from votes.
        
        STRICT RULES (user requirement):
        - ALL agents must agree on the same BUY or SELL direction → TRADE
        - If ANY agent disagrees → NO TRADE (skip)
        - If all HOLD → NO TRADE (skip)
        - If split → debate → still split → NO TRADE
        - Only unanimous BUY or unanimous SELL triggers a trade
        """
        tally = self.tally_votes(votes)
        counts = tally["counts"]
        total = tally["total"]
        
        # Check for unanimous BUY or unanimous SELL
        for direction in ["BUY", "SELL"]:
            if counts[direction] == total:
                # UNANIMOUS — all agents agree
                matching = [v for _, v in votes]
                avg_entry = sum(v["entry"] for v in matching) / len(matching)
                avg_sl = sum(v["stop_loss"] for v in matching) / len(matching)
                avg_tp = sum(v["take_profit"] for v in matching) / len(matching)
                
                reasons = [f"{v['agent_emoji']}{v['reason'][:40]}" for v in matching]
                
                return {
                    "decision": direction,
                    "entry": round(avg_entry, 5),
                    "stop_loss": round(avg_sl, 5),
                    "take_profit": round(avg_tp, 5),
                    "reason": " | ".join(reasons),
                    "confidence": "UNANIMOUS",
                    "vote_counts": counts,
                    "tally": tally,
                    "debate_happened": self.last_debate is not None,
                }
        
        # NOT unanimous — no trade
        dissenters = []
        for agent, vote in votes:
            if vote["decision"] != "HOLD":
                dissenters.append(f"{vote['agent_emoji']}{vote['agent_id'].upper()}:{vote['decision']}")
        
        reason_parts = []
        if counts["BUY"] > 0:
            reason_parts.append(f"BUY×{counts['BUY']}")
        if counts["SELL"] > 0:
            reason_parts.append(f"SELL×{counts['SELL']}")
        if counts["HOLD"] > 0:
            reason_parts.append(f"HOLD×{counts['HOLD']}")
        
        return {
            "decision": "HOLD",
            "entry": 0,
            "stop_loss": 0,
            "take_profit": 0,
            "reason": f"No unanimous agreement ({' '.join(reason_parts)}) — trade skipped",
            "confidence": "NONE",
            "vote_counts": counts,
            "tally": tally,
            "debate_happened": self.last_debate is not None,
        }
    
    def decide(self, window_data, current_price):
        """
        Full council decision flow.
        
        STRICT FLOW:
        1. All agents vote independently
        2. If unanimous on BUY/SELL → TRADE immediately
        3. If NOT unanimous → debate → re-vote
        4. After debate: unanimous → TRADE
        5. After debate: still not unanimous → SKIP (no trade)
        """
        self.last_debate = None
        
        self.log("🏛️  COUNCIL SESSION STARTED", "council")
        
        # Step 1: Collect votes
        self.log("📋 Phase 1: Independent voting...", "council")
        votes = self.collect_votes(window_data, current_price)
        tally = self.tally_votes(votes)
        
        self.log(
            f"📊 Votes: BUY={tally['counts']['BUY']} SELL={tally['counts']['SELL']} "
            f"HOLD={tally['counts']['HOLD']}",
            "council"
        )
        
        # Step 2: Check if unanimous
        if tally["is_unanimous"] and tally["majority_dir"] in ["BUY", "SELL"]:
            self.log(f"✅ UNANIMOUS {tally['majority_dir']} — Trade approved!", "council")
            return self.get_consensus(votes)
        
        # Step 3: Not unanimous → debate
        self.log("🗣️  Not unanimous — Starting debate...", "council")
        
        for round_num in range(self.debate_rounds):
            self.log(f"🔄 Debate round {round_num + 1}/{self.debate_rounds}", "council")
            votes = self.run_debate(votes, window_data, current_price)
            tally = self.tally_votes(votes)
            
            self.log(
                f"📊 After debate: BUY={tally['counts']['BUY']} SELL={tally['counts']['SELL']} "
                f"HOLD={tally['counts']['HOLD']}",
                "council"
            )
            
            # Check if unanimous after debate
            if tally["is_unanimous"] and tally["majority_dir"] in ["BUY", "SELL"]:
                self.log(f"✅ UNANIMOUS after debate: {tally['majority_dir']} — Trade approved!", "council")
                return self.get_consensus(votes)
        
        # Step 4: Still not unanimous → no trade
        self.log("❌ No unanimous consensus — Trade SKIPPED", "council")
        return self.get_consensus(votes)
