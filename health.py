import time
import traceback
from functools import wraps
from core.state import STATE, save_state
from core.utils import now_utc

STATE.setdefault("task_health", {})

def record_start(task_name: str):
    h = STATE["task_health"].setdefault(task_name, {})
    h["last_start"] = now_utc()
    h["running"] = True
    save_state(STATE)
    return time.time()

def record_success(task_name: str, start_ts: float):
    h = STATE["task_health"].setdefault(task_name, {})
    h["running"] = False
    h["last_success"] = now_utc()
    h["last_duration_sec"] = round(time.time() - start_ts, 2)
    h.pop("last_error", None)
    save_state(STATE)

def record_failure(task_name: str, start_ts: float, exc: Exception):
    h = STATE["task_health"].setdefault(task_name, {})
    h["running"] = False
    h["last_failure"] = now_utc()
    h["last_duration_sec"] = round(time.time() - start_ts, 2)
    h["last_error"] = f"{type(exc).__name__}: {exc}"
    h["trace"] = traceback.format_exc(limit=3)
    save_state(STATE)

def monitored_task(task_name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = record_start(task_name)
            try:
                result = await func(*args, **kwargs)
                record_success(task_name, start)
                return result
            except Exception as e:
                record_failure(task_name, start, e)
                raise
        return wrapper
    return decorator
