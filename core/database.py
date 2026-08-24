import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

# =====================================================
# PATHS
# =====================================================
BASE_DIR = os.getenv("KAMANOSUKE_HOME", "/opt/kamanosuke")
STATE_FILE = os.path.join(BASE_DIR, "state.json")
DB_PATH = os.path.join(BASE_DIR, "kamanosuke.db")

_lock = threading.Lock()

# =====================================================
# JSON STATE (USED BY MULTIPLE MODULES)
# =====================================================
def load_state() -> dict:
    with _lock:
        if not os.path.exists(STATE_FILE):
            return {}
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}


def save_state(state: dict):
    with _lock:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_FILE)


# =====================================================
# SQLITE INIT (HIBP + FUTURE)
# =====================================================
def db_init():
    os.makedirs(BASE_DIR, exist_ok=True)

    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()

        # --- HIBP monitored targets (EMAIL / DOMAIN) ---
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS monitored_targets (
                target TEXT PRIMARY KEY,
                target_type TEXT NOT NULL,
                added_at TEXT NOT NULL
            )
            """
        )

        con.commit()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
