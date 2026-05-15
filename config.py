"""
Configuration Manager
Stores API key, model, window size, and other settings.
Persists to config.json so settings survive restarts.
"""

import json
import os
import requests

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "api_key": "",
    "model": "kilo-auto/free",
    "base_url": "https://api.kilo.ai/api/gateway/chat/completions",
    "window_size": 20,
    "pair": "EURUSD",
    "timeframe": "M1",
    "data_file": "",  # will be set dynamically
    "temperature": 0.3,
    "max_tokens": 800,
    # Multi-agent council settings
    "use_council": False,
    "num_agents": 3,           # 3 or 5 agents
    "debate_rounds": 1,        # Number of debate rounds when split
    "consensus_threshold": 0.6, # 60% agreement needed
}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            saved = json.load(f)
            merged = {**DEFAULT_CONFIG, **saved}
            return merged
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def fetch_free_models(api_key: str) -> list:
    """Fetch available models from Kilo Gateway, return only free ones."""
    try:
        resp = requests.get(
            "https://api.kilo.ai/api/gateway/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        
        models = resp.json().get("data", [])
        free_models = []
        
        for m in models:
            pricing = m.get("pricing", {})
            is_free = (
                pricing.get("prompt") == "0"
                and pricing.get("completion") == "0"
                and pricing.get("request") == "0"
            )
            if is_free or ":free" in m.get("id", ""):
                free_models.append({
                    "id": m["id"],
                    "name": m.get("name", m["id"]),
                    "context_length": m.get("context_length", 0),
                    "max_completion_tokens": m.get("top_provider", {}).get("max_completion_tokens", 0),
                })
        
        return free_models
    except Exception as e:
        print(f"Error fetching models: {e}")
        return []
