import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone

import discord

from core.client import client
from core.config import (
    CREEPY_CRAWLIES_FORUM_ID,
    NGINX_ACCESS_LOG,
    SPOOK_SHACK_HOST,
)
from core.database import DB_PATH

# ======================================================
# CONSTANTS
# ======================================================
ALLOWLIST_PATHS = {"/", "/favicon.ico", "/robots.txt", "/404.html"}

LOG_RE = re.compile(
    r'(?P<ip>\S+) \S+ \S+ \[(?P<time>.*?)\] '
    r'"(?P<method>\S+) (?P<path>\S+) \S+" '
    r'(?P<status>\d{3})'
)

LOG_WITH_HOST_RE = re.compile(
    r'(?P<host>\S+)\s+(?P<ip>\S+) \S+ \S+ \[(?P<time>.*?)\] '
    r'"(?P<method>\S+) (?P<path>\S+) \S+" '
    r'(?P<status>\d{3})'
)

# ======================================================
# DATABASE
# ======================================================
def db():
    return sqlite3.connect(DB_PATH)


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def init_tables():
    with db() as con:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS creepy_seen_ips (
                ip TEXT PRIMARY KEY,
                first_seen TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS creepy_state (
                k TEXT PRIMARY KEY,
                v TEXT
            )
            """
        )
        con.commit()


def get_offset():
    with db() as con:
        cur = con.cursor()
        cur.execute("SELECT v FROM creepy_state WHERE k='offset'")
        row = cur.fetchone()
        return int(row[0]) if row else 0


def set_offset(val: int):
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO creepy_state VALUES ('offset', ?)",
            (str(val),),
        )
        con.commit()


def is_new_ip(ip: str) -> bool:
    with db() as con:
        cur = con.cursor()
        cur.execute("SELECT 1 FROM creepy_seen_ips WHERE ip=?", (ip,))
        return cur.fetchone() is None


def mark_ip_seen(ip: str):
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO creepy_seen_ips VALUES (?, ?)",
            (ip, utc_now()),
        )
        con.commit()

# ======================================================
# PARSING
# ======================================================
def normalize_path(path: str) -> str:
    return path.split("?")[0] if path else "/"


def parse_nginx_line(line: str):
    m = LOG_WITH_HOST_RE.search(line)
    if m:
        return {
            "host": (m.group("host") or "").lower(),
            "ip": m.group("ip"),
            "path": m.group("path"),
        }

    m = LOG_RE.search(line)
    if m:
        return {
            "host": None,
            "ip": m.group("ip"),
            "path": m.group("path"),
        }

    return None


def is_interesting(entry: dict) -> bool:
    path = normalize_path(entry["path"])

    if path in ALLOWLIST_PATHS:
        return False

    if entry["host"] and entry["host"] != SPOOK_SHACK_HOST:
        return False

    return True

# ======================================================
# LOG READER (OFFSET SAFE)
# ======================================================
def read_new_lines():
    try:
        size = os.path.getsize(NGINX_ACCESS_LOG)
        offset = get_offset()

        if size < offset:
            offset = 0

        with open(NGINX_ACCESS_LOG, "r", errors="ignore") as f:
            f.seek(offset)
            data = f.read()
            new_offset = f.tell()

        set_offset(new_offset)
        return data.splitlines() if data else []

    except FileNotFoundError:
        print("[Creepy] nginx access log not found")
    except PermissionError:
        print("[Creepy] permission denied reading nginx log")
    except Exception as e:
        print("[Creepy] error:", e)

    return []

# ======================================================
# FORMATTERS (SPOOK SHACK THEME)
# ======================================================
def title(ip_count: int) -> str:
    return (
        "🕷️ Creepy Crawlies Report: 1 new footprint"
        if ip_count == 1
        else f"🕸️ Creepy Crawlies Report: {ip_count} new footprints"
    )


def body(ip_count: int, paths: Counter) -> str:
    if ip_count == 0:
        count_line = "No fresh footprints… but something brushed past the walls."
    elif ip_count == 1:
        count_line = "We uncovered **1** fresh footprint in the dust."
    else:
        count_line = f"We uncovered **{ip_count}** fresh footprints in the dust."

    top = paths.most_common(3)
    insight = ""
    if top:
        insight = "🧠 **Most rattled doors:** " + " | ".join(
            f"`{p}` ({c})" for p, c in top
        )

    return (
        "👻 **Spook Shack Perimeter Sweep**\n"
        f"🕯️ **Inspection Time:** {utc_now()}\n\n"
        "The Shack was quiet… until something started clawing at the doors.\n\n"
        f"{count_line}\n\n"
        f"{insight}\n\n"
        "🕷️ Full details manifest below.\n"
        "🧹 Repeat offenders are already warded away."
    )


def format_paths(counter: Counter, limit=12):
    if not counter:
        return "🧠 No meaningful path activity this cycle."

    lines = [f"- `{p}` — **{c}** hit(s)" for p, c in counter.most_common(limit)]
    return "🧠 **Most Prodded Entry Points**\n" + "\n".join(lines)

# ======================================================
# MAIN REPORTER
# ======================================================
async def post_creepy_crawlies():
    init_tables()

    forum = client.get_channel(CREEPY_CRAWLIES_FORUM_ID)
    if not isinstance(forum, discord.ForumChannel):
        return

    new_ips = set()
    path_counter = Counter()

    for line in read_new_lines():
        entry = parse_nginx_line(line)
        if not entry:
            continue
        if not is_interesting(entry):
            continue

        path = normalize_path(entry["path"])
        path_counter[path] += 1

        ip = entry["ip"]
        if is_new_ip(ip):
            new_ips.add(ip)

    if not new_ips and not path_counter:
        return

    thread = await forum.create_thread(
        name=title(len(new_ips)),
        content=body(len(new_ips), path_counter),
    )
    t = thread.thread

    await t.send(format_paths(path_counter))

    if new_ips:
        await t.send(
            "🧾 **New Crawlies (never seen before)**\n"
            + "\n".join(f"- `{ip}`" for ip in sorted(new_ips))
        )

        for ip in new_ips:
            mark_ip_seen(ip)
    else:
        await t.send(
            "🧾 **New Crawlies**\n"
            "None this cycle — whatever it was, it fled."
        )

# ======================================================
# EXPORTED LOOP (CALLED BY main.py)
# ======================================================
async def creepy_crawlies_loop():
    await post_creepy_crawlies()
