"""
Multi-Agent Trading Council — Roundtable Meeting Style

Flow:
1. OPENING STATEMENTS: Each agent analyzes data independently, presents their case
2. ROUNDTABLE DISCUSSION: All agents see each other's arguments, respond, try to convince
3. FINAL VOTE: After discussion, agents cast final votes
4. CONSENSUS: Majority wins, no majority = no trade
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
        "default_model": "kilo-auto/free",
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
        "default_model": "kilo-auto/free",
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
        "default_model": "kilo-auto/free",
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
        "default_model": "kilo-auto/free",
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
        "default_model": "kilo-auto/free",
        "system_prompt": (
            "You are Epsilon, a contrarian trader. You look for exhaustion and reversal signals. "
            "When everyone is buying, you look to sell. When everyone is selling, you look to buy. "
            "You watch for long wicks, failed breakouts, and divergence. "
            "You are skeptical of strong moves — they often reverse. Set wide TP, tight SL."
        ),
    },
]


# ─── Prompts ────────────────────────────────────────────────────────

OPENING_STATEMENT_PROMPT = """You are {name}, sitting at a roundtable with other Forex traders.
Everyone is analyzing the same EUR/USD data. It's your turn to present your opening analysis.

YOUR TRADING STYLE:
{system_prompt}

THE DATA:
Current price: {price}
Last 20 candles:
{candle_table}

YOUR TASK:
Present your analysis to the group. Be specific about what YOU see in the data.
End with your clear position.

FORMAT — Your LAST lines must be:
POSITION: [BUY/SELL/HOLD]
ENTRY: [price or 0]
STOP_LOSS: [price or 0]
TAKE_PROFIT: [price or 0]

Then on the line before POSITION, give your REASONING (2-3 sentences max).
Explain what patterns/momentum/signals YOU see that support your position."""


ROUNDTABLE_PROMPT = """You are {name} at a roundtable meeting with other Forex traders.
Everyone has presented their analysis of EUR/USD. Now it's time for OPEN DISCUSSION.

THE DATA:
Current price: {price}
Last 20 candles:
{candle_table}

═══ EVERYONE'S OPENING STATEMENTS ═══

{all_statements}

═══ DISCUSSION RULES ═══

1. Read what others said carefully. They might see something you missed.
2. If someone makes a good point that changes your mind, SAY SO.
3. If you think someone is wrong, explain WHY with specific evidence from the data.
4. You can ask questions to other agents.
5. Be direct. No fluff. Talk like a trader at a desk, not a professor.

At the END of your response, put EXACTLY one of:
FINAL_VOTE: BUY
FINAL_VOTE: SELL
FINAL_VOTE: HOLD

If you changed your mind from your opening statement, explain why.
If you're sticking to your original position, defend it."""


MODERATOR_PROMPT = """You are a neutral trading floor moderator. Here are the final votes from {num_agents} traders after a roundtable discussion:

{votes_summary}

RULES:
- Count the votes for BUY, SELL, and HOLD
- If 2+ out of 3 (or 3+ out of 5) agree on BUY or SELL → that's the consensus
- If votes are evenly split → HOLD (no trade)

Respond with EXACTLY:
CONSENSUS: [BUY/SELL/HOLD]
CONFIDENCE: [HIGH/MEDIUM/LOW]
REASON: [1 sentence summary of the discussion]"""


# ─── Council Class ──────────────────────────────────────────────────


class TradingCouncil:
    """
    Roundtable meeting style multi-agent council.
    
    Flow:
    1. Each agent presents opening statement (independent analysis)
    2. Roundtable discussion (agents see each other's arguments)
    3. Final votes cast
    4. Majority consensus determines trade
    """
    
    def __init__(self, config):
        self.config = config
        num_agents = config.get("num_agents", 3)
        self.agents = AGENT_PROFILES[:num_agents]
        self.debate_rounds = config.get("debate_rounds", 1)
        self.log_callback = None
        self.last_debate = None
        
        # Per-agent model mapping
        self.agent_models = config.get("agent_models", {})
        for agent in self.agents:
            agent["model"] = self.agent_models.get(
                agent["id"],
                agent.get("default_model", config.get("model", "kilo-auto/free"))
            )
        
        # Majority threshold
        self.majority_threshold = num_agents // 2 + 1
    
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
    
    def call_llm(self, agent, system_prompt, user_prompt, max_tokens=500):
        """Call LLM API using the agent's assigned model."""
        model = agent.get("model", self.config.get("model", "kilo-auto/free"))
        try:
            resp = requests.post(
                self.config["base_url"],
                headers={
                    "Authorization": f"Bearer {self.config['api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
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
                self.log(f"API error ({model}): {resp.status_code}", "error")
                return None
            data = resp.json()
            message = data["choices"][0]["message"]
            content = message.get("content", "") or ""
            reasoning = message.get("reasoning", "") or ""
            if not content.strip() and reasoning:
                content = reasoning
            return {
                "content": content.strip(),
                "reasoning": reasoning.strip(),
                "model": data.get("model", model),
            }
        except Exception as e:
            self.log(f"LLM call failed ({model}): {e}", "error")
            return None
    
    def parse_position(self, content):
        """Parse POSITION or FINAL_VOTE from response text."""
        result = {"decision": "HOLD", "entry": 0, "stop_loss": 0, "take_profit": 0, "reason": ""}
        lines = content.split("\n")
        
        for line in lines:
            clean = line.strip().upper()
            
            # Match POSITION or FINAL_VOTE
            if ("POSITION" in clean or "FINAL_VOTE" in clean) and ":" in clean:
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
        
        return result
    
    # ── Phase 1: Opening Statements ─────────────────────────────────
    
    def collect_opening_statements(self, window_data, current_price):
        """Each agent presents their independent analysis."""
        candle_table = self.build_candle_table(window_data, current_price)
        statements = []
        
        for agent in self.agents:
            model_name = agent.get("model", "unknown")
            self.log(f"  {agent['emoji']} {agent['name']} presenting... [{model_name}]", "agent_vote")
            
            prompt = OPENING_STATEMENT_PROMPT.format(
                name=agent["name"],
                system_prompt=agent["system_prompt"],
                price=current_price,
                candle_table=candle_table,
            )
            
            response = self.call_llm(agent, agent["system_prompt"], prompt, max_tokens=500)
            
            if response:
                parsed = self.parse_position(response["content"])
                parsed["raw"] = response["content"]
                parsed["reasoning"] = response.get("reasoning", "")
                parsed["model"] = response.get("model", "unknown")
            else:
                parsed = {
                    "decision": "HOLD", "entry": 0, "stop_loss": 0, "take_profit": 0,
                    "reason": "No response", "raw": "", "model": "N/A",
                }
            
            parsed["agent_id"] = agent["id"]
            parsed["agent_name"] = agent["name"]
            parsed["agent_emoji"] = agent["emoji"]
            
            statements.append((agent, parsed))
            
            # Log the full opening statement to the live feed
            self.log(f"  {agent['emoji']} {agent['name']}:", "agent_vote")
            if response and response.get("reasoning"):
                self.log(f"  💭 {response['reasoning'][:300]}", "thinking")
            for line in parsed.get("raw", "").split("\n"):
                line = line.strip()
                if line:
                    self.log(f"  {agent['emoji']} {line}", "agent_vote")
            self.log(
                f"  {agent['emoji']} → {parsed['decision']} | Entry: {parsed['entry']} | "
                f"SL: {parsed['stop_loss']} | TP: {parsed['take_profit']}",
                "decision"
            )
        
        return statements
    
    # ── Phase 2: Roundtable Discussion ──────────────────────────────
    
    def run_roundtable(self, statements, window_data, current_price):
        """All agents discuss, see each other's arguments, may change their minds."""
        candle_table = self.build_candle_table(window_data, current_price)
        
        # Build the "all statements" block
        statement_lines = []
        for agent, vote in statements:
            statement_lines.append(
                f"{vote['agent_emoji']} {vote['agent_name']}:\n"
                f"  Position: {vote['decision']}\n"
                f"  Entry: {vote['entry']} | SL: {vote['stop_loss']} | TP: {vote['take_profit']}\n"
                f"  Reasoning: {vote['reason']}\n"
            )
        all_statements = "\n".join(statement_lines)
        
        self.log("🗣️  ROUNDTABLE DISCUSSION STARTING", "council")
        self.log("  All agents presenting arguments to each other...", "council")
        
        discussion_log = []
        discussion_log.append("=" * 60)
        discussion_log.append("🗣️  ROUNDTABLE DISCUSSION")
        discussion_log.append("=" * 60)
        
        revised_votes = []
        
        for agent, vote in statements:
            prompt = ROUNDTABLE_PROMPT.format(
                name=agent["name"],
                price=current_price,
                candle_table=candle_table,
                all_statements=all_statements,
            )
            
            self.log(f"  {agent['emoji']} {agent['id'].upper()} discussing...", "debate")
            
            response = self.call_llm(agent, agent["system_prompt"], prompt, max_tokens=600)
            
            if response:
                content = response["content"]
                discussion_log.append(f"\n{agent['emoji']} {agent['name']}:")
                discussion_log.append(content[:500])
                
                # Log the ACTUAL discussion content to the live feed
                # Split into readable chunks
                for line in content.split("\n"):
                    line = line.strip()
                    if line:
                        self.log(f"  {agent['emoji']} {agent['id'].upper()}: {line}", "debate")
                
                # Parse final vote from discussion
                revised = self.parse_position(content)
                
                # Keep original SL/TP if discussion didn't provide new ones
                if revised["entry"] == 0 and vote["entry"] > 0:
                    revised["entry"] = vote["entry"]
                    revised["stop_loss"] = vote["stop_loss"]
                    revised["take_profit"] = vote["take_profit"]
                
                revised["agent_id"] = agent["id"]
                revised["agent_name"] = agent["name"]
                revised["agent_emoji"] = agent["emoji"]
                revised["raw"] = content
                revised["model"] = response.get("model", agent.get("model", "unknown"))
                
                # Log if they changed their mind
                if revised["decision"] != vote["decision"]:
                    self.log(
                        f"  {agent['emoji']} {agent['id'].upper()} CHANGED MIND: "
                        f"{vote['decision']} → {revised['decision']}",
                        "debate"
                    )
                else:
                    self.log(
                        f"  {agent['emoji']} {agent['id'].upper()} STICKS WITH: {revised['decision']}",
                        "debate"
                    )
                
                revised_votes.append((agent, revised))
            else:
                # Keep original vote if discussion fails
                revised_votes.append((agent, vote))
        
        self.last_debate = "\n".join(discussion_log)
        return revised_votes
    
    # ── Phase 3: Consensus ──────────────────────────────────────────
    
    def tally_votes(self, votes):
        """Count votes."""
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
            "has_majority": majority_count >= self.majority_threshold,
            "is_unanimous": majority_count == total,
        }
    
    def get_consensus(self, votes):
        """Determine final consensus from votes."""
        tally = self.tally_votes(votes)
        counts = tally["counts"]
        
        # Check if any direction has majority
        for direction in ["BUY", "SELL"]:
            if counts[direction] >= self.majority_threshold:
                matching_votes = [v for _, v in votes if v["decision"] == direction]
                avg_entry = sum(v["entry"] for v in matching_votes) / len(matching_votes)
                avg_sl = sum(v["stop_loss"] for v in matching_votes) / len(matching_votes)
                avg_tp = sum(v["take_profit"] for v in matching_votes) / len(matching_votes)
                
                reasons = [f"{v['agent_emoji']}{v['reason'][:50]}" for v in matching_votes]
                confidence = "HIGH" if counts[direction] == tally["total"] else "MEDIUM"
                
                return {
                    "decision": direction,
                    "entry": round(avg_entry, 5),
                    "stop_loss": round(avg_sl, 5),
                    "take_profit": round(avg_tp, 5),
                    "reason": " | ".join(reasons),
                    "confidence": confidence,
                    "vote_counts": counts,
                    "tally": tally,
                    "debate_happened": self.last_debate is not None,
                }
        
        # No majority
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
            "reason": f"No majority ({' '.join(reason_parts)}) — no trade",
            "confidence": "NONE",
            "vote_counts": counts,
            "tally": tally,
            "debate_happened": self.last_debate is not None,
        }
    
    # ── Main Flow ───────────────────────────────────────────────────
    
    def decide(self, window_data, current_price):
        """
        Full roundtable meeting flow:
        
        1. OPENING STATEMENTS — each agent presents independently
        2. ROUNDTABLE DISCUSSION — agents see each other's arguments, debate
        3. FINAL VOTE — after discussion, agents cast final votes
        4. CONSENSUS — majority wins
        """
        self.last_debate = None
        
        self.log("🏛️  ROUNDTABLE MEETING STARTED", "council")
        for agent in self.agents:
            self.log(f"  {agent['emoji']} {agent['id'].upper()} → {agent['model']}", "council")
        
        # Phase 1: Opening Statements
        self.log("📋 Phase 1: Opening Statements — each agent presents their analysis", "council")
        statements = self.collect_opening_statements(window_data, current_price)
        tally = self.tally_votes(statements)
        
        self.log(
            f"📊 Opening positions: BUY={tally['counts']['BUY']} SELL={tally['counts']['SELL']} "
            f"HOLD={tally['counts']['HOLD']}",
            "council"
        )
        
        # Phase 2: Roundtable Discussion
        if self.debate_rounds > 0:
            self.log("🗣️  Phase 2: Roundtable Discussion", "council")
            final_votes = self.run_roundtable(statements, window_data, current_price)
            
            # Multiple rounds if configured
            for round_num in range(1, self.debate_rounds):
                self.log(f"🔄 Discussion round {round_num + 1}/{self.debate_rounds}", "council")
                final_votes = self.run_roundtable(final_votes, window_data, current_price)
        else:
            self.log("⏭️  Discussion skipped (debate_rounds=0)", "council")
            final_votes = statements
        
        # Phase 3: Final Consensus
        tally = self.tally_votes(final_votes)
        self.log(
            f"📊 Final votes: BUY={tally['counts']['BUY']} SELL={tally['counts']['SELL']} "
            f"HOLD={tally['counts']['HOLD']} | Need {self.majority_threshold}/{tally['total']}",
            "council"
        )
        
        consensus = self.get_consensus(final_votes)
        
        if consensus["decision"] in ["BUY", "SELL"]:
            self.log(f"✅ CONSENSUS: {consensus['decision']} (confidence: {consensus['confidence']})", "council")
        else:
            self.log(f"❌ NO CONSENSUS — no trade", "council")
        
        return consensus
