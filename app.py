"""
Forex Trading Agent — Web Dashboard
Flask app for managing and monitoring the trading agent.
"""

from flask import Flask, render_template, request, jsonify
import threading
import json
import os
from config import load_config, save_config, fetch_free_models
from agent import TradingAgent
from huggingface_hub import hf_hub_download

app = Flask(__name__)

# Global state
agent = None
log_buffer = []  # Stores recent log messages for polling
config = load_config()

# Download data files from HuggingFace on startup
DATA_REPO = "Raihan1234/forex-agent-data"
DATA_FILES = ["EURUSD_M1_February_2026.parquet", "EURUSD_M1_March_2026.parquet"]
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

def download_data():
    """Download parquet data files from HuggingFace dataset."""
    # Try to find a valid HF token
    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if hf_token:
        print(f"  🔑 HF token found ({hf_token[:8]}...)")
    else:
        print("  🔑 No HF token found — dataset is public, downloading without auth")
    
    for fname in DATA_FILES:
        fpath = os.path.join(DATA_DIR, fname)
        if os.path.exists(fpath):
            print(f"  ✅ Already exists: {fname}")
            continue
        
        # Try with token first, then without
        attempts = [
            ("with token", hf_token if hf_token else True),
            ("without token", None),
        ]
        
        for attempt_name, token_val in attempts:
            try:
                print(f"  ⬇ Downloading {fname} ({attempt_name})...")
                hf_hub_download(
                    repo_id=DATA_REPO,
                    repo_type="dataset",
                    filename=fname,
                    local_dir=DATA_DIR,
                    token=token_val,
                )
                print(f"  ✅ Downloaded: {fname}")
                break
            except Exception as e:
                print(f"  ⚠ {attempt_name} failed: {type(e).__name__}: {e}")
        else:
            print(f"  ❌ All attempts failed for {fname}")
    
    # Verify files
    downloaded = [f for f in os.listdir(DATA_DIR) if f.endswith(".parquet")]
    print(f"  📂 Data directory contents: {downloaded}")
    if not downloaded:
        print("  ⚠⚠⚠ WARNING: No data files available! Backtest will not work.")
        print("  💡 Fix: Set HF_TOKEN in Space settings, or upload parquet files manually")

print("📥 Downloading data files...")
download_data()


def log_callback(msg, level="info"):
    """Called by agent to send log messages to dashboard."""
    log_buffer.append({"msg": msg, "level": level, "ts": str(__import__("datetime").datetime.now())})
    # Keep only last 500 messages
    if len(log_buffer) > 500:
        log_buffer.pop(0)


# ─── Routes ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("dashboard.html", config=config)


@app.route("/api/config", methods=["GET"])
def get_config():
    safe = config.copy()
    if safe.get("api_key"):
        key = safe["api_key"]
        safe["api_key"] = key[:6] + "..." + key[-4:] if len(key) > 12 else "***"
    return jsonify(safe)


@app.route("/api/config", methods=["POST"])
def update_config():
    global config
    data = request.json
    config.update(data)
    save_config(config)
    return jsonify({"status": "ok", "config": config})


@app.route("/api/models", methods=["POST"])
def list_models():
    """Fetch free models from Kilo Gateway."""
    api_key = request.json.get("api_key", config.get("api_key", ""))
    if not api_key:
        return jsonify({"error": "API key required"}), 400
    
    models = fetch_free_models(api_key)
    return jsonify({"models": models})


@app.route("/api/data/files", methods=["GET"])
def list_data_files():
    """List available parquet files."""
    files = []
    if os.path.exists(DATA_DIR):
        for f in os.listdir(DATA_DIR):
            if f.endswith(".parquet"):
                size = os.path.getsize(os.path.join(DATA_DIR, f))
                files.append({"name": f, "size_kb": round(size / 1024, 1)})
    return jsonify({"files": files})


@app.route("/api/data/download", methods=["POST"])
def redownload_data():
    """Trigger re-download of data files from HuggingFace."""
    download_data()
    files = []
    if os.path.exists(DATA_DIR):
        for f in os.listdir(DATA_DIR):
            if f.endswith(".parquet"):
                size = os.path.getsize(os.path.join(DATA_DIR, f))
                files.append({"name": f, "size_kb": round(size / 1024, 1)})
    return jsonify({"files": files, "count": len(files)})


@app.route("/api/start", methods=["POST"])
def start_agent():
    """Start or resume the trading agent."""
    global agent
    
    data = request.json or {}
    data_file = data.get("data_file", config.get("data_file", ""))
    
    if not data_file:
        return jsonify({"error": "No data file selected"}), 400
    
    if not config.get("api_key"):
        return jsonify({"error": "API key not set"}), 400
    
    filepath = os.path.join(DATA_DIR, data_file)
    if not os.path.exists(filepath):
        return jsonify({"error": f"File not found: {data_file}"}), 400
    
    if agent and agent.is_running and agent.is_paused:
        agent.is_paused = False
        log_callback("▶ Resumed", "system")
        return jsonify({"status": "resumed"})
    
    # Create new agent
    agent = TradingAgent(config)
    agent.set_log_callback(log_callback)
    
    total = agent.load_data(filepath)
    log_callback(f"📂 Loaded {data_file} | {total:,} candles", "system")
    
    max_candles = data.get("max_candles", None)
    
    # Run in background thread
    thread = threading.Thread(target=agent.run_backtest, args=(max_candles,), daemon=True)
    thread.start()
    
    return jsonify({"status": "started", "total_candles": total})


@app.route("/api/pause", methods=["POST"])
def pause_agent():
    global agent
    if agent and agent.is_running:
        agent.is_paused = True
        log_callback("⏸ Paused", "system")
        return jsonify({"status": "paused"})
    return jsonify({"error": "No running agent"}), 400


@app.route("/api/stop", methods=["POST"])
def stop_agent():
    global agent
    if agent:
        agent.is_running = False
        agent.is_paused = False
        log_callback("⏹ Stopped", "system")
        return jsonify({"status": "stopped"})
    return jsonify({"error": "No agent"}), 400


@app.route("/api/status", methods=["GET"])
def get_status():
    """Get current agent status, stats, and recent logs."""
    global agent
    
    result = {
        "running": False,
        "paused": False,
        "stats": None,
        "trades": [],
        "active_trade": None,
        "candle_index": 0,
        "total_candles": 0,
        "logs": log_buffer[-50:],  # Last 50 messages
    }
    
    if agent:
        result["running"] = agent.is_running
        result["paused"] = agent.is_paused
        result["candle_index"] = agent.current_index
        result["total_candles"] = len(agent.df) if agent.df is not None else 0
        result["stats"] = agent.get_stats()
        result["trades"] = agent.get_trades_list()
        
        if agent.active_trade:
            result["active_trade"] = agent.active_trade.to_dict()
    
    return jsonify(result)


@app.route("/api/save", methods=["POST"])
def save_trades():
    """Save trade log to CSV."""
    global agent
    if agent and agent.trades:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "trade_log.csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        agent.save_trades_csv(path)
        return jsonify({"status": "saved", "path": path})
    return jsonify({"error": "No trades to save"}), 400


# ─── Run ──────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"), exist_ok=True)
    port = int(os.environ.get("PORT", 7860))
    print("\n" + "=" * 50)
    print("  FOREX TRADING AGENT DASHBOARD")
    print(f"  Open: http://localhost:{port}")
    print("=" * 50 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
