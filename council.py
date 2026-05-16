"""
Multi-Agent Trading Council — Roundtable Meeting (Unanimous Consensus)

All agents receive the EXACT SAME data and the EXACT SAME prompt.
The only difference is the MODEL each agent uses.
Different LLMs naturally interpret data differently — that's the diversity.

FLOW:
1. All agents get identical data + identical prompt
2. Each presents their independent analysis
3. They see each other's opinions and discuss
4. Must reach 100% unanimous agreement
5. If not unanimous → HOLD (no trade)
"""

import requests
import json
import time
import threading


# ─── System Prompt (shared by ALL agents) ───────────────────────────

SHARED_SYSTEM_PROMPT = (
    "You are a professional Forex trader analyzing EUR/USD M1 (1-minute) candle data. "
    "You are sitting at a roundtable with other traders. Everyone is looking at the same data. "
    "Give your honest, independent analysis. Be direct and specific. "
    "Use evidence from the candle data to support your position."
)


# ─── Prompts ────────────────────────────────────────────────────────

OPENING_STATEMENT_PROMPT = """You are Agent {agent_num} at a roundtable with {total_agents} Forex traders.
Everyone is analyzing the EXACT SAME EUR/USD data. It's your turn to present your analysis.

THE DATA (this is the SAME data every other trader is seeing):
Current price: {price}
Last 20 candles:
{candle_table}

YOUR TASK:
Analyze the price action and present your honest assessment.
Look at trend, momentum, support/resistance, candle patterns, volume — whatever matters.
End with your clear position.

FORMAT — Your LAST lines must be:
POSITION: [BUY/SELL/HOLD]
ENTRY: [price or 0]
STOP_LOSS: [price or 0]
TAKE_PROFIT: [price or 0]

On the line before POSITION, give your REASONING (2-3 sentences max).
Explain what YOU see in the data that supports your position."""


DEBATE_PROMPT = """You are Agent {agent_num} at a roundtable with {total_agents} Forex traders.
Everyone has presented their analysis. Now it's time for discussion.

THE DATA (same data everyone is looking at):
Current price: {price}
Last 20 candles:
{candle_table}

═══ WHAT EVERYONE SAID ═══

{all_statements}

═══ CURRENT VOTE SPLIT ═══
{vote_summary}

═══ DISCUSSION RULES ═══

1. Read what the others said carefully. They might see something you missed.
2. If someone makes a good point that changes your mind, SAY SO. It's okay to change.
3. If you think someone is wrong, explain WHY with specific evidence from the data.
4. Be direct. Talk like a trader at a desk, not a professor.
5. Use SPECIFIC prices and patterns from the candle data.

At the END of your response, put EXACTLY one of:
FINAL_VOTE: BUY
FINAL_VOTE: SELL
FINAL_VOTE: HOLD

If you changed your mind, explain why.
If you're sticking with your original position, defend it."""


# ─── Council Class ──────────────────────────────────────────────────


class TradingCouncil:
    """
    Roundtable where all agents are EQUAL.
    Same prompt, same data, different models.
    Unanimous consensus required.
    """

    def __init__(self, config):
        self.config = config
        self.debate_rounds = config.get("debate_rounds", 1)
        self.log_callback = None
        self.last_debate = None
        self.is_running = True  # Set to False to cancel

        # Build agent list from selected_agents + their models
        selected = config.get("selected_agents", [])
        agent_models = config.get("agent_models", {})

        if selected:
            self.agents = []
            for i, agent_id in enumerate(selected):
                model = agent_models.get(agent_id, config.get("model", "kilo-auto/free"))
                self.agents.append({
                    "id": agent_id,
                    "num": i + 1,
                    "model": model,
                })
        else:
            # Fallback: 3 agents with default model
            default_model = config.get("model", "kilo-auto/free")
            self.agents = [
                {"id": f"agent_{i+1}", "num": i + 1, "model": default_model}
                for i in range(config.get("num_agents", 3))
            ]

    def set_log_callback(self, callback):
        self.log_callback = callback

    def log(self, msg, level="info"):
        if self.log_callback:
            self.log_callback(msg, level)
        print(f"[{level.upper()}] {msg}")

    def build_candle_table(self, window_data, current_price):
        """Build IDENTICAL candle table for all agents."""
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

    def call_llm(self, agent, user_prompt, max_tokens=500):
        """Call LLM API. Cancellable — checks is_running while waiting."""
        model = agent["model"]
        result = [None]
        error = [None]

        def _do_request():
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
                            {"role": "system", "content": SHARED_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": max_tokens,
                        "temperature": self.config.get("temperature", 0.3),
                    },
                    timeout=120,
                )
                if resp.status_code != 200:
                    error[0] = f"API error ({model}): {resp.status_code}"
                    return
                data = resp.json()
                message = data["choices"][0]["message"]
                content = message.get("content", "") or ""
                reasoning = message.get("reasoning", "") or ""
                if not content.strip() and reasoning:
                    content = reasoning
                result[0] = {
                    "content": content.strip(),
                    "reasoning": reasoning.strip(),
                    "model": data.get("model", model),
                }
            except requests.exceptions.Timeout:
                error[0] = "TIMEOUT"
            except Exception as e:
                error[0] = str(e)

        thread = threading.Thread(target=_do_request, daemon=True)
        thread.start()

        # Wait but check is_running every second
        while thread.is_alive():
            if not self.is_running:
                self.log("⏹ Cancelled — stopping API call", "system")
                return None
            thread.join(timeout=1)

        if error[0]:
            if error[0] == "TIMEOUT":
                self.log(f"⏰ TIMEOUT: {model} did not respond in 120s", "error")
            else:
                self.log(f"❌ ERROR ({model}): {error[0]}", "error")
            return None

        return result[0]

    def parse_position(self, content):
        """Parse POSITION or FINAL_VOTE from response text."""
        result = {
            "decision": "HOLD",
            "entry": 0,
            "stop_loss": 0,
            "take_profit": 0,
            "reason": "",
        }
        lines = content.split("\n")

        for line in lines:
            clean = line.strip().upper()

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
                    result["entry"] = float(''.join(
                        c for c in clean.split(":", 1)[1] if c.isdigit() or c == '.' or c == '-'
                    ))
                except:
                    pass

            if ("STOP_LOSS" in clean or "STOP LOSS" in clean) and ":" in clean:
                try:
                    result["stop_loss"] = float(''.join(
                        c for c in clean.split(":", 1)[1] if c.isdigit() or c == '.' or c == '-'
                    ))
                except:
                    pass

            if ("TAKE_PROFIT" in clean or "TAKE PROFIT" in clean) and ":" in clean:
                try:
                    result["take_profit"] = float(''.join(
                        c for c in clean.split(":", 1)[1] if c.isdigit() or c == '.' or c == '-'
                    ))
                except:
                    pass

            if "REASON" in clean and ":" in line:
                result["reason"] = line.split(":", 1)[1].strip()

        return result

    # ── Phase 1: Opening Statements ─────────────────────────────────

    def collect_opening_statements(self, window_data, current_price):
        """
        All agents get the SAME data and SAME prompt.
        Only difference: each uses a different model.
        """
        candle_table = self.build_candle_table(window_data, current_price)
        statements = []

        self.log("━" * 50, "council")
        self.log("📋 PHASE 1: OPENING STATEMENTS", "council")
        self.log(f"  {len(self.agents)} agents | Same data, same prompt, different models", "council")
        self.log("━" * 50, "council")

        for agent in self.agents:
            self.log(f"🤖 Agent {agent['num']} [{agent['model']}] — waiting for response...", "loading")

            prompt = OPENING_STATEMENT_PROMPT.format(
                agent_num=agent["num"],
                total_agents=len(self.agents),
                price=current_price,
                candle_table=candle_table,
            )

            response = self.call_llm(agent, prompt, max_tokens=500)

            if response:
                parsed = self.parse_position(response["content"])
                parsed["raw"] = response["content"]
                parsed["reasoning"] = response.get("reasoning", "")
                parsed["model"] = response.get("model", agent["model"])
            else:
                parsed = {
                    "decision": "HOLD", "entry": 0, "stop_loss": 0, "take_profit": 0,
                    "reason": "No response", "raw": "", "model": "N/A",
                }

            parsed["agent_id"] = agent["id"]
            parsed["agent_num"] = agent["num"]

            statements.append((agent, parsed))

            # Log the statement
            self.log(f"  🤖 Agent {agent['num']} [{parsed['model']}]:", "agent_vote")
            if response and response.get("reasoning"):
                self.log(f"  💭 {response['reasoning'][:300]}", "thinking")
            for line in parsed.get("raw", "").split("\n"):
                line = line.strip()
                if line:
                    self.log(f"  🤖 {line}", "agent_vote")
            self.log(
                f"  🤖 Agent {agent['num']} → {parsed['decision']} | Entry: {parsed['entry']} | "
                f"SL: {parsed['stop_loss']} | TP: {parsed['take_profit']}",
                "decision"
            )

        return statements

    # ── Phase 2: Discussion ─────────────────────────────────────────

    def build_vote_summary(self, votes):
        """Build summary of who voted what."""
        counts = {"BUY": [], "SELL": [], "HOLD": []}
        for agent, vote in votes:
            counts[vote["decision"]].append(f"Agent {agent['num']}")

        lines = []
        for direction in ["BUY", "SELL", "HOLD"]:
            if counts[direction]:
                lines.append(f"  {direction}: {', '.join(counts[direction])}")
        return "\n".join(lines)

    def run_discussion(self, votes, window_data, current_price):
        """
        All agents see each other's opinions and discuss.
        They can change their minds based on what others say.
        """
        candle_table = self.build_candle_table(window_data, current_price)
        vote_summary = self.build_vote_summary(votes)

        # Build "what everyone said" block
        statement_lines = []
        for agent, vote in votes:
            statement_lines.append(
                f"Agent {agent['num']} ({agent['model']}):\n"
                f"  Position: {vote['decision']}\n"
                f"  Entry: {vote['entry']} | SL: {vote['stop_loss']} | TP: {vote['take_profit']}\n"
                f"  Reasoning: {vote['reason']}\n"
            )
        all_statements = "\n".join(statement_lines)

        self.log("━" * 50, "council")
        self.log("🗣️  PHASE 2: DISCUSSION", "council")
        self.log("  All agents see each other's opinions and discuss", "council")
        self.log("━" * 50, "council")

        revised_votes = []

        for agent, vote in votes:
            prompt = DEBATE_PROMPT.format(
                agent_num=agent["num"],
                total_agents=len(self.agents),
                price=current_price,
                candle_table=candle_table,
                all_statements=all_statements,
                vote_summary=vote_summary,
            )

            self.log(f"🤖 Agent {agent['num']} [{agent['model']}] — waiting for response...", "loading")

            response = self.call_llm(agent, prompt, max_tokens=600)

            if response:
                content = response["content"]

                for line in content.split("\n"):
                    line = line.strip()
                    if line:
                        self.log(f"  🤖 Agent {agent['num']}: {line}", "debate")

                revised = self.parse_position(content)

                # Keep original SL/TP if discussion didn't provide new ones
                if revised["entry"] == 0 and vote["entry"] > 0:
                    revised["entry"] = vote["entry"]
                    revised["stop_loss"] = vote["stop_loss"]
                    revised["take_profit"] = vote["take_profit"]

                revised["agent_id"] = agent["id"]
                revised["agent_num"] = agent["num"]
                revised["raw"] = content
                revised["model"] = response.get("model", agent["model"])

                if revised["decision"] != vote["decision"]:
                    self.log(
                        f"  🤖 Agent {agent['num']} CHANGED MIND: "
                        f"{vote['decision']} → {revised['decision']}",
                        "debate"
                    )
                else:
                    self.log(
                        f"  🤖 Agent {agent['num']} STICKS WITH: {revised['decision']}",
                        "debate"
                    )

                revised_votes.append((agent, revised))
            else:
                revised_votes.append((agent, vote))

        return revised_votes

    # ── Phase 3: Unanimous Consensus ────────────────────────────────

    def tally_votes(self, votes):
        """Count votes."""
        counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
        for agent, vote in votes:
            counts[vote["decision"]] += 1

        total = len(votes)
        unanimous_dir = None
        for direction in ["BUY", "SELL", "HOLD"]:
            if counts[direction] == total:
                unanimous_dir = direction

        return {
            "counts": counts,
            "total": total,
            "unanimous_dir": unanimous_dir,
            "is_unanimous": unanimous_dir is not None,
        }

    def get_consensus(self, votes):
        """
        UNANIMOUS consensus only.
        ALL agents must agree. If even one disagrees → HOLD.
        """
        tally = self.tally_votes(votes)
        counts = tally["counts"]

        self.log("━" * 50, "council")
        self.log("📊 PHASE 3: FINAL CONSENSUS", "council")
        self.log(
            f"  Votes: BUY={counts['BUY']} SELL={counts['SELL']} HOLD={counts['HOLD']} "
            f"| {tally['total']} agents",
            "council"
        )

        if tally["is_unanimous"]:
            direction = tally["unanimous_dir"]

            if direction in ["BUY", "SELL"]:
                matching = [v for _, v in votes if v["decision"] == direction]
                avg_entry = sum(v["entry"] for v in matching) / len(matching)
                avg_sl = sum(v["stop_loss"] for v in matching) / len(matching)
                avg_tp = sum(v["take_profit"] for v in matching) / len(matching)
                reasons = [f"A{v['agent_num']}: {v['reason'][:50]}" for v in matching]

                self.log(f"  ✅ UNANIMOUS: {direction} — TRADE APPROVED", "council")

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
            else:
                self.log("  ✅ UNANIMOUS: HOLD — No trade", "council")
                return {
                    "decision": "HOLD",
                    "entry": 0,
                    "stop_loss": 0,
                    "take_profit": 0,
                    "reason": "All agents agree — no trade",
                    "confidence": "UNANIMOUS",
                    "vote_counts": counts,
                    "tally": tally,
                    "debate_happened": self.last_debate is not None,
                }
        else:
            dissenters = []
            for d in ["BUY", "SELL", "HOLD"]:
                if counts[d] > 0 and counts[d] < tally["total"]:
                    dissenters.append(f"{d}×{counts[d]}")

            self.log(f"  ❌ NO UNANIMOUS CONSENSUS — No trade", "council")
            self.log(f"  Split: {' '.join(dissenters)}", "council")

            return {
                "decision": "HOLD",
                "entry": 0,
                "stop_loss": 0,
                "take_profit": 0,
                "reason": f"Not unanimous ({' '.join(dissenters)}) — no trade",
                "confidence": "NONE",
                "vote_counts": counts,
                "tally": tally,
                "debate_happened": self.last_debate is not None,
            }

    # ── Main Flow ───────────────────────────────────────────────────

    def decide(self, window_data, current_price):
        """
        Full roundtable meeting:
        1. All agents get identical data + prompt, present analysis
        2. Discussion — they see each other's opinions, can change minds
        3. Final vote — must be 100% unanimous
        """
        self.last_debate = None

        self.log("🏛️  " + "=" * 46, "council")
        self.log("🏛️  ROUNDTABLE MEETING STARTED", "council")
        self.log("🏛️  " + "=" * 46, "council")
        self.log(f"  Participants: {len(self.agents)} agents", "council")
        for agent in self.agents:
            self.log(f"  🤖 Agent {agent['num']} → {agent['model']}", "council")
        self.log(f"  Rule: UNANIMOUS consensus required", "council")
        self.log("  " + "-" * 46, "council")

        # Phase 1: Opening Statements
        statements = self.collect_opening_statements(window_data, current_price)
        tally = self.tally_votes(statements)

        self.log(
            f"📊 Opening: BUY={tally['counts']['BUY']} SELL={tally['counts']['SELL']} "
            f"HOLD={tally['counts']['HOLD']}",
            "council"
        )

        # Phase 2: Discussion (if not unanimous and debate_rounds > 0)
        if self.debate_rounds > 0 and not tally["is_unanimous"]:
            self.log("🗣️  Positions differ — discussion starting", "council")
            final_votes = statements

            for round_num in range(self.debate_rounds):
                self.log(f"\n🔄 Discussion round {round_num + 1}/{self.debate_rounds}", "council")
                final_votes = self.run_discussion(final_votes, window_data, current_price)

                round_tally = self.tally_votes(final_votes)
                if round_tally["is_unanimous"]:
                    self.log(f"✅ Unanimous after round {round_num + 1}!", "council")
                    break

            self.last_debate = True
        elif tally["is_unanimous"]:
            self.log("✅ Already unanimous — no discussion needed", "council")
            final_votes = statements
        else:
            final_votes = statements

        # Phase 3: Final Consensus
        consensus = self.get_consensus(final_votes)

        self.log("🏛️  " + "=" * 46, "council")

        return consensus
