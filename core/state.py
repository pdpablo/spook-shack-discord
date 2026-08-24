import json
import os
from pathlib import Path

BASE_DIR = Path(os.getenv("KAMANOSUKE_HOME", "/opt/kamanosuke"))
STATE_FILE = BASE_DIR / "state.json"


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state):
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, STATE_FILE)


STATE = load_state()
