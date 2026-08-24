import feedparser
import hashlib
import re
from datetime import datetime, timezone, date

from discord.ext import tasks
import discord

from core.client import client
from core.config import (
    PARANORMAL_DISCUSSION_CHANNEL_ID,
    SHACK_LOUNGE_CHANNEL_ID,
    OPENAI_API_KEY,
)
from core.database import load_state, save_state
from core.health import monitored_task
from core.openai_client import openai_chat

# =====================================================
# LOCAL DEFAULTS (MATCH ORIGINAL SCRIPT)
# =====================================================
OPENAI_MODEL = "gpt-4o-mini"

# =====================================================
# CURATED PARANORMAL SOURCES
# =====================================================
PARANORMAL_FEEDS = [
    "https://www.forteantimes.com/feed/",
    "https://www.theblackvault.com/documentarchive/feed/",
    "https://phys.org/rss-feed/earth-news/",
    "https://www.ancient-origins.net/rss.xml",
]

# =====================================================
# HTML CLEANING (FIXES TAG LEAK)
# =====================================================
HTML_RE = re.compile(r"<[^>]+>")

def strip_html(text: str) -> str:
    if not text:
        return ""
    text = HTML_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


# =====================================================
# UTILITIES
# =====================================================
def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def article_uid(entry) -> str:
    base = (entry.get("link", "") + entry.get("title", "")).encode()
    return hashlib.sha256(base).hexdigest()


# =====================================================
# FORMAT (MATCHES YOUR ORIGINAL SCRIPT)
# =====================================================
def format_article_post(title, source, link, summary, insight):
    return (
        f"🕯️ **Paranormal Dispatch** 🕯️\n\n"
        f"📖 **Title:** {title}\n"
        f"📰 **Source:** {source}\n"
        f"🕰️ **Observed:** {now_utc()}\n\n"
        f"🧾 **What surfaced**\n"
        f"{summary}\n\n"
        f"🧠 **Spook Shack Insight**\n"
        f"{insight}\n\n"
        f"💬 **The Shack asks:**\n"
        f"- Coincidence, misinterpretation… or something else?\n"
        f"- What non-paranormal explanation fits best?\n"
        f"- Have similar cases appeared before?\n\n"
        f"🔗 {link}"
    )


# =====================================================
# OPENAI PROMPT (UNCHANGED LOGIC)
# =====================================================
def insight_prompt(title: str, summary: str):
    return [
        {
            "role": "system",
            "content": (
                "You are a rational, skeptical-but-open analyst discussing "
                "paranormal and anomalous reports in a community called Spook Shack.\n"
                "You do NOT claim events are supernatural.\n"
                "You explore plausible explanations: natural, psychological, "
                "technological, or unknown.\n"
                "Tone: grounded, curious, conversational.\n"
                "Avoid sensationalism."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Article title: {title}\n\n"
                f"Summary:\n{summary}\n\n"
                "Provide a short insight (4–6 sentences) that:\n"
                "- explains why this is interesting\n"
                "- suggests rational explanations\n"
                "- invites discussion"
            ),
        },
    ]


# =====================================================
# PARANORMAL ARTICLE POSTER
# =====================================================
async def post_paranormal_article(entry):
    channel = client.get_channel(PARANORMAL_DISCUSSION_CHANNEL_ID)
    if not channel:
        return

    title = strip_html(entry.get("title", "Untitled"))
    link = entry.get("link")
    source = entry.get("source", {}).get("title", "Unknown Source")

    raw_summary = (
        entry.get("summary")
        or entry.get("description")
        or ""
    )

    summary = strip_html(raw_summary)[:700]

    insight = "No AI insight available."
    if OPENAI_API_KEY:
        insight = await openai_chat(
            insight_prompt(title, summary),
            model=OPENAI_MODEL,
            temperature=0.4,
            max_tokens=220,
        )

    content = format_article_post(
        title=title,
        source=source,
        link=link,
        summary=summary,
        insight=insight,
    )

    if len(content) > 1900:
        content = content[:1900] + "\n\n*(truncated)*"

    await channel.send(content)


# =====================================================
# FETCH + DEDUP (MATCHES ORIGINAL)
# =====================================================
async def fetch_and_post(limit=1):
    state = load_state()
    seen = set(state.get("paranormal_seen", []))
    new_seen = set(seen)

    posted = 0

    for feed_url in PARANORMAL_FEEDS:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries:
            uid = article_uid(entry)
            if uid in seen:
                continue

            await post_paranormal_article(entry)
            new_seen.add(uid)
            posted += 1

            if posted >= limit:
                state["paranormal_seen"] = list(new_seen)[-500:]
                save_state(state)
                return

    state["paranormal_seen"] = list(new_seen)[-500:]
    save_state(state)


# =====================================================
# PARANORMAL DISCUSSION — EVERY 6 HOURS
# =====================================================
@tasks.loop(hours=6)
@monitored_task("paranormal_discussion")
async def paranormal_loop():
    if not PARANORMAL_DISCUSSION_CHANNEL_ID:
        return
    await fetch_and_post(limit=1)


async def run_paranormal_once():
    if not PARANORMAL_DISCUSSION_CHANNEL_ID:
        return
    await fetch_and_post(limit=1)


# =====================================================
# SHACK LOUNGE — ONCE PER DAY (NO DUPLICATES)
# =====================================================
@tasks.loop(hours=24)
@monitored_task("shack_lounge")
async def lounge_loop():
    channel = client.get_channel(SHACK_LOUNGE_CHANNEL_ID)
    if not channel:
        return

    state = load_state()
    today = str(date.today())

    if state.get("lounge_last_posted") == today:
        return  # prevent duplicates

    await channel.send(
        "🕯️ **Late Night at the Shack** 🕯️\n\n"
        "What’s the strangest unexplained thing you’ve personally witnessed?\n"
        "Stick to facts — no embellishment."
    )

    state["lounge_last_posted"] = today
    save_state(state)
