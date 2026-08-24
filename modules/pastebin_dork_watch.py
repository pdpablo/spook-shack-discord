import aiohttp
import asyncio
import sqlite3
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, parse_qs, unquote, urlparse

import discord
from discord.ext import tasks

from core.client import client
from core.config import PASTEBIN_CHANNEL_ID
from core.database import DB_PATH
from core.health import monitored_task

# ======================================================
# CONFIG
# ======================================================
CHECK_INTERVAL_HOURS = 1

DORK_TEMPLATE = (
    'site:pastebin.com "{kw}" OR '
    'site:ghostbin.com "{kw}" OR '
    'site:paste.ee "{kw}" OR '
    'site:paste.mozilla.org "{kw}" OR '
    'site:hastebin.com "{kw}"'
)

DDG_SEARCH = "https://duckduckgo.com/html/?q="

# ======================================================
# IOC REGEX
# ======================================================
IOC_REGEX = {
    "emails": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "aws_keys": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic_tokens": re.compile(r"(?i)(api[_-]?key|token|secret)[\"'=:\s]+[a-z0-9-_]{16,64}"),
    "passwords": re.compile(r"(?i)(password|passwd|pwd)[\"'=:\s]+.+"),
}

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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS paste_keywords (
                keyword TEXT PRIMARY KEY,
                added_at TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS paste_dork_hits (
                keyword TEXT,
                url TEXT,
                PRIMARY KEY (keyword, url)
            )
        """)

        con.commit()


def get_keywords():
    with db() as con:
        cur = con.cursor()
        cur.execute("SELECT keyword FROM paste_keywords")
        return [r[0] for r in cur.fetchall()]


def add_keyword(kw):
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO paste_keywords VALUES (?, ?)",
            (kw.lower(), utc_now()),
        )
        con.commit()


def remove_keyword(kw):
    with db() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM paste_keywords WHERE keyword=?", (kw.lower(),))
        con.commit()


def is_new_hit(kw, url):
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT 1 FROM paste_dork_hits WHERE keyword=? AND url=?",
            (kw, url),
        )
        return cur.fetchone() is None


def mark_hit(kw, url):
    with db() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO paste_dork_hits VALUES (?, ?)",
            (kw, url),
        )
        con.commit()

# ======================================================
# DORK SEARCH
# ======================================================
LINK_RE = re.compile(r'href="([^"]+)"')


def _extract_ddg_url(href: str) -> str | None:
    if not href:
        return None

    if href.startswith("//"):
        href = "https:" + href

    if href.startswith("https://duckduckgo.com/l/?") or "uddg=" in href:
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        uddg = params.get("uddg", [None])[0]
        if uddg:
            return unquote(uddg)
        return None

    return href if href.startswith("http") else None


async def dork_search(session, keyword):
    dork = DORK_TEMPLATE.format(kw=keyword)
    url = DDG_SEARCH + quote_plus(dork)

    headers = {"User-Agent": "Mozilla/5.0 (SpookShack-Intel)"}

    async with session.get(url, headers=headers, timeout=30) as r:
        if r.status != 200:
            return []

        html = await r.text()
        seen = []
        for href in LINK_RE.findall(html):
            candidate = _extract_ddg_url(href)
            if not candidate:
                continue
            if any(p in candidate.lower() for p in ["pastebin.com", "ghostbin.com", "paste.ee", "paste.mozilla.org", "hastebin.com"]):
                seen.append(candidate.split("&")[0])

        out = []
        for item in seen:
            if item not in out:
                out.append(item)
        return out[:10]

# ======================================================
# IOC EXTRACTION
# ======================================================
def extract_iocs(text: str):
    findings = {}
    for name, regex in IOC_REGEX.items():
        matches = set(regex.findall(text))
        if matches:
            findings[name] = list(matches)[:10]
    return findings

# ======================================================
# FORMATTER (SPOOK SHACK)
# ======================================================
def alert(keyword, url, iocs):
    lines = [
        "🕯️ **Whispers from the Paste Realm** 🕯️",
        "",
        f"🧿 **Keyword:** `{keyword}`",
        f"🕰️ **Detected:** {utc_now()}",
        "",
        f"🔗 {url.replace('https://', 'hxxps://').replace('.', '[.]')}",
        "",
    ]

    if iocs:
        lines.append("🧬 **Extracted IOCs**")
        for k, vals in iocs.items():
            lines.append(f"**{k}:**")
            for v in vals:
                lines.append(f"- `{v}`")

    lines.append("")
    lines.append("⚠️ Manual validation recommended.")

    return "\n".join(lines)

# ======================================================
# HOURLY MONITOR
# ======================================================
@tasks.loop(hours=CHECK_INTERVAL_HOURS)
@monitored_task("paste_dork_watch")
async def paste_dork_monitor():
    init_tables()
    keywords = get_keywords()

    if not keywords or not PASTEBIN_CHANNEL_ID:
        return

    channel = client.get_channel(PASTEBIN_CHANNEL_ID)
    if not channel:
        return

    async with aiohttp.ClientSession() as session:
        for kw in keywords:
            urls = await dork_search(session, kw)

            for url in urls:
                if not is_new_hit(kw, url):
                    continue

                mark_hit(kw, url)

                # Try to fetch content for IOC scan
                content = ""
                try:
                    async with session.get(url, timeout=15) as r:
                        if r.status == 200:
                            content = await r.text()
                except Exception:
                    pass

                iocs = extract_iocs(content)
                await channel.send(alert(kw, url, iocs))

            await asyncio.sleep(5)

# ======================================================
# SAFE START
# ======================================================
def start_paste_dork_monitor():
    if not paste_dork_monitor.is_running():
        paste_dork_monitor.start()

# ======================================================
# COMMAND HANDLER
# ======================================================
async def handle_paste_dork(message: discord.Message):
    if not message.content.lower().startswith("!paste"):
        return False

    parts = message.content.split()
    if len(parts) < 2:
        await message.channel.send(
            "🕯️ **Paste Watch (Dorking)** 🕯️\n"
            "`!paste add <keyword>`\n"
            "`!paste remove <keyword>`\n"
            "`!paste list`\n"
            "`!paste quick <keyword>`"
        )
        return True

    cmd = parts[1].lower()

    if cmd == "list":
        kws = get_keywords()
        if not kws:
            await message.channel.send("🕯️ No bound keywords.")
            return True
        await message.channel.send(
            "🧿 **Paste Watch Keywords** 🧿\n" + "\n".join(f"- `{k}`" for k in kws)
        )
        return True

    if cmd in {"add", "remove"} and len(parts) >= 3:
        kw = parts[2].lower()
        if cmd == "add":
            add_keyword(kw)
            await message.channel.send(f"🕯️ `{kw}` bound to the Paste Ward.")
        else:
            remove_keyword(kw)
            await message.channel.send(f"🧹 `{kw}` banished from the Paste Ward.")
        return True

    if cmd == "quick" and len(parts) >= 3:
        kw = parts[2].lower()
        await message.channel.send(f"🕯️ Searching for `{kw}`…")

        async with aiohttp.ClientSession() as session:
            urls = await dork_search(session, kw)

        if not urls:
            await message.channel.send("🕯️ No whispers detected.")
            return True

        for url in urls[:5]:
            await message.channel.send(alert(kw, url, {}))

        return True

    await message.channel.send("❌ Invalid paste command.")
    return True
