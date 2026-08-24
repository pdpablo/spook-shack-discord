import requests
import discord
import json
import os
from discord.ext import tasks
from dotenv import load_dotenv
from telethon import TelegramClient

from core.client import client

# ===== LOAD ENV =====
load_dotenv()

MISP_FEED_URL = os.getenv("MISP_FEED_URL")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 3600))

# Discord channels
CHANNELS = {
    "ransomware": int(os.getenv("CHANNEL_RANSOMWARE", "0") or 0),
    "vulnerability": int(os.getenv("CHANNEL_VULNERABILITY", "0") or 0),
    "apt": int(os.getenv("CHANNEL_APT", "0") or 0),
    "general": int(os.getenv("CHANNEL_GENERAL", "0") or 0),
    "breach": int(os.getenv("CHANNEL_BREACH", "0") or 0),
}

# Telegram
TG_API_ID_RAW = os.getenv("TG_API_ID", "").strip()
TG_API_HASH = os.getenv("TG_API_HASH", "").strip()
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
TG_CHANNEL = os.getenv("TG_CHANNEL", "").strip()
TG_API_ID = int(TG_API_ID_RAW) if TG_API_ID_RAW else 0
TELEGRAM_ENABLED = bool(TG_API_ID and TG_API_HASH and TG_CHANNEL)
TELEGRAM_BOT_MODE = bool(TELEGRAM_ENABLED and TG_BOT_TOKEN)

# State files
MISP_STATE_FILE = "seen_events.json"
TG_STATE_FILE = "seen_telegram.txt"

# ====================

tg_client = TelegramClient("tg_session", TG_API_ID, TG_API_HASH) if TELEGRAM_ENABLED else None

# ---------- STATE HELPERS ----------

def load_seen_events():
    if os.path.exists(MISP_STATE_FILE):
        with open(MISP_STATE_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_events(seen):
    with open(MISP_STATE_FILE, "w") as f:
        json.dump(list(seen), f)

def load_last_tg_id():
    if os.path.exists(TG_STATE_FILE):
        try:
            with open(TG_STATE_FILE, "r") as f:
                return int(f.read().strip())
        except Exception:
            return 0
    return 0

def save_last_tg_id(msg_id):
    with open(TG_STATE_FILE, "w") as f:
        f.write(str(msg_id))

# ---------- MISP HELPERS ----------

def parse_tags(tags):
    parsed = {"types": [], "threat_level": "unknown", "tlp": "unknown"}

    for tag in tags:
        name = tag.get("name", "").lower()
        if name.startswith("type:"):
            parsed["types"].append(name.split("type:")[1])
        elif name.startswith("threat-level:"):
            parsed["threat_level"] = name.split("threat-level:")[1]
        elif name.startswith("tlp:"):
            parsed["tlp"] = name.split("tlp:")[1]

    return parsed

def choose_channel(types):
    if "ransomware" in types:
        return CHANNELS["ransomware"]
    if "vulnerability" in types:
        return CHANNELS["vulnerability"]
    if "apt" in types or "malware" in types:
        return CHANNELS["apt"]
    return CHANNELS["general"]

# ---------- MISP POLLER ----------

@tasks.loop(seconds=POLL_INTERVAL)
async def poll_misp():
    seen = load_seen_events()

    try:
        resp = requests.get(MISP_FEED_URL, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        for event_id, event in data.items():
            if event_id in seen:
                continue

            tags = parse_tags(event.get("Tag", []))
            channel = client.get_channel(choose_channel(tags["types"]))
            if not channel:
                continue

            embed = discord.Embed(
                title="🚨 ThreatCluster Intelligence",
                description=event.get("info", "No title"),
                color=discord.Color.red() if tags["threat_level"] == "high" else discord.Color.orange()
            )

            embed.add_field(name="Type",
                            value=", ".join(tags["types"]) if tags["types"] else "general",
                            inline=True)
            embed.add_field(name="Threat Level",
                            value=tags["threat_level"],
                            inline=True)
            embed.add_field(name="TLP",
                            value=tags["tlp"],
                            inline=True)
            embed.add_field(name="Date",
                            value=event.get("date", "N/A"),
                            inline=True)

            embed.set_footer(text=f"Source: {event.get('Orgc', {}).get('name', 'ThreatCluster')}")

            await channel.send(embed=embed)
            seen.add(event_id)

        save_seen_events(seen)

    except Exception:
        pass

# ---------- TELEGRAM POLLER (PRODUCTION CLEAN VERSION) ----------

@tasks.loop(seconds=POLL_INTERVAL)
async def poll_telegram():
    try:
        if not TELEGRAM_ENABLED or tg_client is None:
            return

        if not tg_client.is_connected():
            if TELEGRAM_BOT_MODE:
                await tg_client.start(bot_token=TG_BOT_TOKEN)
            else:
                await tg_client.connect()

        if TELEGRAM_BOT_MODE:
            if not tg_client.is_connected():
                return
        elif not await tg_client.is_user_authorized():
            return

        entity = await tg_client.get_entity(f"@{TG_CHANNEL.lstrip('@')}")
        last_id = load_last_tg_id()

        discord_channel = client.get_channel(CHANNELS["breach"])
        if not discord_channel:
            return

        max_id = last_id
        offset_id = last_id

        while True:
            messages = await tg_client.get_messages(
                entity,
                min_id=offset_id,
                limit=100
            )

            if not messages:
                break

            for msg in reversed(messages):
                if not msg.message:
                    continue

                if msg.id <= last_id:
                    continue

                await discord_channel.send(msg.message[:1900])
                max_id = max(max_id, msg.id)

            offset_id = max(m.id for m in messages)

            if len(messages) < 100:
                break

        if max_id > last_id:
            save_last_tg_id(max_id)

    except Exception:
        pass

# ---------- DISCORD EVENTS ----------
