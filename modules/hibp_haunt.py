import aiohttp
import sqlite3
import asyncio
from datetime import datetime, timezone, date

import discord
from discord.ext import tasks

from core.client import client
from core.config import HIBP_API_KEY, SPOOK_CHANNEL_ID
from core.database import DB_PATH
from core.health import monitored_task

# ======================================================
# CONSTANTS
# ======================================================
HIBP_BASE = "https://haveibeenpwned.com/api/v3"
HIBP_DELAY = 2.0  # HIBP-safe delay (seconds)

HEADERS = {
    "hibp-api-key": HIBP_API_KEY,
    "user-agent": "SpookShack-Haunt/FINAL",
}

# ======================================================
# DATABASE HELPERS
# ======================================================
def db():
    return sqlite3.connect(DB_PATH)


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def init_tables():
    with db() as con:
        cur = con.cursor()

        # Deduplicate breaches forever
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hibp_seen (
                target TEXT,
                breach TEXT,
                PRIMARY KEY (target, breach)
            )
            """
        )

        # Daily digest marker
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hibp_digest (
                day TEXT PRIMARY KEY
            )
            """
        )

        con.commit()


def get_targets():
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT target, target_type FROM monitored_targets ORDER BY added_at ASC"
        )
        return cur.fetchall()


def add_target(target, target_type):
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO monitored_targets VALUES (?, ?, ?)",
            (target, target_type, utc_now()),
        )
        con.commit()


def remove_target(target, target_type):
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "DELETE FROM monitored_targets WHERE target=? AND target_type=?",
            (target, target_type),
        )
        con.commit()


def is_new_breach(target, breach):
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT 1 FROM hibp_seen WHERE target=? AND breach=?",
            (target, breach),
        )
        return cur.fetchone() is None


def mark_seen(target, breach):
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO hibp_seen VALUES (?, ?)",
            (target, breach),
        )
        con.commit()


def digest_sent_today():
    today = date.today().isoformat()
    with db() as con:
        cur = con.cursor()
        cur.execute("SELECT 1 FROM hibp_digest WHERE day=?", (today,))
        return cur.fetchone() is not None


def mark_digest_sent():
    today = date.today().isoformat()
    with db() as con:
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO hibp_digest VALUES (?)", (today,))
        con.commit()

# ======================================================
# FORMATTERS
# ======================================================
def format_breach_block(b):
    return (
        f"👁️ **{b.get('Name', b.get('Title', 'Unknown'))}**\n"
        f"Breach Date: {b.get('BreachDate', 'Unknown')}\n"
        f"Added: {b.get('AddedDate', 'Unknown')[:10] if b.get('AddedDate') else 'Unknown'}\n"
        f"Records: {b.get('PwnCount', 'Unknown')}\n"
        f"Exposed Data: {', '.join(b.get('DataClasses', [])) or 'Unknown'}\n"
        f"Flags: {'✅ Verified' if b.get('IsVerified') else '⚠️ Unverified'}\n"
    )


def chunk(text, limit=1900):
    out, buf = [], ""
    for line in text.splitlines():
        if len(buf) + len(line) > limit:
            out.append(buf)
            buf = line
        else:
            buf += ("\n" if buf else "") + line
    if buf:
        out.append(buf)
    return out

# ======================================================
# HIBP API (FULL RESPONSE FIX APPLIED)
# ======================================================
async def hibp_lookup(session, target, target_type):
    if target_type == "email":
        # IMPORTANT: FULL breach details
        url = f"{HIBP_BASE}/breachedaccount/{target}?truncateResponse=false"
    else:
        url = f"{HIBP_BASE}/breaches?domain={target}"

    async with session.get(url, headers=HEADERS) as resp:
        if resp.status in (404, 429):
            return []
        if resp.status != 200:
            return []
        return await resp.json()

# ======================================================
# HOURLY FULL SCAN
# ======================================================
@tasks.loop(hours=1)
@monitored_task("hibp_hourly")
async def haunt_monitor():
    init_tables()

    channel = client.get_channel(SPOOK_CHANNEL_ID)
    if not channel:
        return

    targets = get_targets()
    if not targets:
        return

    print(f"[HIBP] Hourly scan started ({len(targets)} targets)", flush=True)

    found_any = False
    summary = []

    async with aiohttp.ClientSession() as session:
        for target, ttype in targets:
            breaches = await hibp_lookup(session, target, ttype)

            for b in breaches:
                name = b.get("Name") or b.get("Title")
                if not name:
                    continue

                if not is_new_breach(target, name):
                    continue

                found_any = True
                mark_seen(target, name)

                report = (
                    "🕯️ **Breach Entities Manifested** 🕯️\n"
                    f"Target: {target}\n"
                    f"Scan: Hourly {ttype.capitalize()} Scan\n\n"
                    "Detected **1** new breach record.\n\n"
                    f"{format_breach_block(b)}"
                )

                for part in chunk(report):
                    await channel.send(part)

                summary.append(f"- {target}: {name}")

            await asyncio.sleep(HIBP_DELAY)

    if not found_any:
        await channel.send(
            "🕯️ **HIBP Hourly Sweep Complete** 🕯️\n"
            "No breaches detected for any monitored emails or domains.\n"
            f"Targets checked: **{len(targets)}**\n"
            f"Time: {utc_now()}"
        )

    # DAILY DIGEST
    if not digest_sent_today():
        digest = (
            "📜 **HIBP Daily Digest** 📜\n\n"
            f"Targets monitored: **{len(targets)}**\n"
            f"New breaches today: **{len(summary)}**\n\n"
        )

        if summary:
            digest += "\n".join(summary)
        else:
            digest += "🕯️ No breaches detected today."

        for part in chunk(digest):
            await channel.send(part)

        mark_digest_sent()

# ======================================================
# SAFE START (USED BY main.py)
# ======================================================
def start_haunt_monitor():
    if not haunt_monitor.is_running():
        haunt_monitor.start()

# ======================================================
# COMMAND HANDLER
# ======================================================
async def handle_haunt(message: discord.Message):
    if not message.content.lower().startswith("!haunt"):
        return False

    parts = message.content.split()
    if len(parts) < 2:
        await message.channel.send(
            "🕯️ **Haunt Commands** 🕯️\n"
            "`!haunt add email someone@x.com`\n"
            "`!haunt add domain example.com`\n"
            "`!haunt quick email someone@x.com`\n"
            "`!haunt quick domain example.com`\n"
            "`!haunt remove email someone@x.com`\n"
            "`!haunt remove domain example.com`\n"
            "`!haunt list`"
        )
        return True

    action = parts[1].lower()

    # LIST
    if action == "list":
        rows = get_targets()
        if not rows:
            await message.channel.send("🕯️ No monitored emails or domains.")
            return True

        msg = ["🕯️ **Haunt Watchlist** 🕯️"]
        for t, tt in rows:
            msg.append(f"- `{t}` ({tt})")

        await message.channel.send("\n".join(msg))
        return True

    # ADD / REMOVE
    if action in {"add", "remove"} and len(parts) >= 4:
        ttype = parts[2].lower()
        target = parts[3].lower()

        if ttype not in {"email", "domain"}:
            await message.channel.send("Type must be `email` or `domain`.")
            return True

        if action == "add":
            add_target(target, ttype)
            await message.channel.send(
                f"🕯️ `{target}` has been **bound to the haunt watchlist**."
            )
            return True

        remove_target(target, ttype)
        await message.channel.send(
            f"🕯️ `{target}` has been **banished from the haunt watchlist**."
        )
        return True

    # QUICK SCAN
    if action == "quick" and len(parts) >= 4:
        ttype = parts[2].lower()
        target = parts[3].lower()

        if ttype not in {"email", "domain"}:
            await message.channel.send("Type must be `email` or `domain`.")
            return True

        await message.channel.send(
            f"🕯️ Summoning breach echoes for `{target}`…"
        )

        async with aiohttp.ClientSession() as session:
            breaches = await hibp_lookup(session, target, ttype)

        if not breaches:
            await message.channel.send(
                f"🕯️ No breaches found for `{target}`."
            )
            return True

        report = (
            "🕯️ **Breach Entities Manifested** 🕯️\n"
            f"Target: {target}\n"
            f"Scan: Quick {ttype.capitalize()} Scan\n\n"
            f"Detected **{len(breaches)}** breach record(s).\n\n"
        )

        for b in breaches:
            report += format_breach_block(b) + "\n"

        for part in chunk(report):
            await message.channel.send(part)

        return True

    await message.channel.send("❌ Invalid haunt command.")
    return True
