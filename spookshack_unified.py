#!/usr/bin/env python3
# ==========================================================
# Spook Shack — Unified Threat Intelligence Bot
# ENV-NORMALIZED VERSION
# ==========================================================

import os
import re
import json
import ssl
import time
import socket
import sqlite3
import asyncio
from datetime import datetime, timedelta, timezone
from collections import Counter
from typing import Optional

import aiohttp
import discord
from discord.ext import tasks, commands
from dotenv import load_dotenv
import feedparser
from openai import AsyncOpenAI

# ==========================================================
# LOAD ENV
# ==========================================================
load_dotenv()

# Paid APIs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HIBP_API_KEY = os.getenv("HIBP_API_KEY")
OTX_API_KEY = os.getenv("OTX_API_KEY")

# Discord core
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Public channels
SIGNAL_ENTRY_CHANNEL_ID = int(os.getenv("SIGNAL_ENTRY_CHANNEL_ID"))
PARANORMAL_DISCUSSION_CHANNEL_ID = int(os.getenv("PARANORMAL_DISCUSSION_CHANNEL_ID"))
SHACK_LOUNGE_CHANNEL_ID = int(os.getenv("SHACK_LOUNGE_CHANNEL_ID"))

# Inner Shack
PH_CHANNEL_ID = int(os.getenv("PH_CHANNEL_ID"))
GLOBAL_CHANNEL_ID = int(os.getenv("GLOBAL_CHANNEL_ID"))
NVD_CVE_CHANNEL_ID = int(os.getenv("NVD_CVE_CHANNEL_ID"))
CHANNEL_BREACH = int(os.getenv("CHANNEL_BREACH"))
SPOOK_CHANNEL_ID = int(os.getenv("SPOOK_CHANNEL_ID"))

# ThreatCluster (MISP)
MISP_FEED_URL = os.getenv("MISP_FEED_URL")
CHANNEL_RANSOMWARE = int(os.getenv("CHANNEL_RANSOMWARE"))
CHANNEL_VULNERABILITY = int(os.getenv("CHANNEL_VULNERABILITY"))
CHANNEL_APT = int(os.getenv("CHANNEL_APT"))
CHANNEL_GENERAL = int(os.getenv("CHANNEL_GENERAL"))

# Restricted / forums
THREAT_ACTOR_FORUM_ID = int(os.getenv("THREAT_ACTOR_FORUM_ID"))
CHANNEL_ONION = int(os.getenv("CHANNEL_ONION"))
SEARCH_CHANNEL_ID = int(os.getenv("SEARCH_CHANNEL_ID"))
CREEPY_CRAWLIES_FORUM_ID = int(os.getenv("CREEPY_CRAWLIES_FORUM_ID"))
TAKEDOWN_COMMAND_CHANNEL_ID = int(os.getenv("TAKEDOWN_COMMAND_CHANNEL_ID"))
TAKEDOWN_FORUM_CHANNEL_ID = int(os.getenv("TAKEDOWN_FORUM_CHANNEL_ID"))
REPORT_COMMAND_CHANNEL_ID = int(os.getenv("REPORT_COMMAND_CHANNEL_ID"))
REPORT_FORUM_CHANNEL_ID = int(os.getenv("REPORT_FORUM_CHANNEL_ID"))


# External feeds
RANSOMWARELIVE_API_TOKEN = os.getenv("RANSOMWARELIVE_API_TOKEN")
NVD_API_KEY = os.getenv("NVD_API_KEY")

# Runtime config
ONION_FILE = os.getenv("ONION_FILE")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "3600"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

if not DISCORD_BOT_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is required")

# ==========================================================
# DISCORD CLIENT (SINGLE)
# ==========================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================================
# OPENAI
# ==========================================================
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ==========================================================
# HTTP SESSION
# ==========================================================
http_session: aiohttp.ClientSession | None = None
TOR_SOCKS = "socks5h://127.0.0.1:9050"

# ==========================================================
# STATE
# ==========================================================
STATE_FILE = "spookshack_state.json"

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

STATE = load_state()

# ==========================================================
# SQLITE (HIBP)
# ==========================================================
DB_PATH = "spookshack.db"

def db_init():
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS monitored_targets(
                target TEXT,
                target_type TEXT,
                added_at TEXT,
                UNIQUE(target, target_type)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS known_breaches(
                target TEXT,
                target_type TEXT,
                breach_name TEXT,
                first_seen_at TEXT,
                UNIQUE(target, target_type, breach_name)
            )
        """)
        con.commit()

# ==========================================================
# HELPERS
# ==========================================================
def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def defang(text: str) -> str:
    return text.replace(".", "[.]") if text else "N/A"

def chunk_text(text: str, limit=1900):
    if len(text) <= limit:
        return [text]
    out, buf = [], ""
    for line in text.splitlines():
        if len(buf) + len(line) + 1 > limit:
            out.append(buf)
            buf = line
        else:
            buf += ("\n" if buf else "") + line
    if buf:
        out.append(buf)
    return out

async def safe_send(dest, text: str):
    for chunk in chunk_text(text):
        await dest.send(chunk)
        await asyncio.sleep(0.4)

# ==========================================================
# RATE LIMITER
# ==========================================================
class RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.time()
            self.calls = [c for c in self.calls if now - c < self.period]
            if len(self.calls) >= self.max_calls:
                await asyncio.sleep(self.period - (now - self.calls[0]))
            self.calls.append(time.time())

hibp_limiter = RateLimiter(10, 60)

# ==========================================================
# MISP FEED (ThreatCluster)
# ==========================================================
@tasks.loop(seconds=POLL_INTERVAL)
async def poll_misp():
    if not MISP_FEED_URL:
        return

    seen = set(STATE.get("misp_seen", []))

    try:
        async with http_session.get(MISP_FEED_URL) as r:
            data = await r.json()

        for eid, event in data.items():
            if eid in seen:
                continue

            tags = [t.get("name", "").lower() for t in event.get("Tag", [])]

            if any("ransomware" in t for t in tags):
                channel = client.get_channel(CHANNEL_RANSOMWARE)
            elif any("vulnerability" in t for t in tags):
                channel = client.get_channel(CHANNEL_VULNERABILITY)
            elif any("apt" in t or "malware" in t for t in tags):
                channel = client.get_channel(CHANNEL_APT)
            else:
                channel = client.get_channel(CHANNEL_GENERAL)

            if not channel:
                continue

            embed = discord.Embed(
                title="🚨 ThreatCluster Intelligence",
                description=event.get("info", "No description"),
                color=discord.Color.orange()
            )
            await channel.send(embed=embed)
            seen.add(eid)

        STATE["misp_seen"] = list(seen)
        save_state(STATE)

    except Exception as e:
        print("[MISP ERROR]", e)


# ==========================================================
# DISCORD READY
# ==========================================================
@client.event
async def on_ready():
    global http_session

    print(f"[+] Logged in as {client.user}")

    connector = aiohttp.TCPConnector(
        family=socket.AF_INET,
        ssl=ssl.create_default_context()
    )
    http_session = aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=30)
    )

    db_init()
    poll_misp.start()

    print("[+] All systems operational 🕯️")

# ==========================================================
# START
# ==========================================================
client.run(DISCORD_BOT_TOKEN)
