import aiohttp
from urllib.parse import quote_plus
from discord.ext import tasks
import discord

from core.client import client
from core.config import (
    RANSOMWARELIVE_API_TOKEN,
    GLOBAL_CHANNEL_ID,
    SEARCH_CHANNEL_ID,
    POLL_INTERVAL,
)
from core.database import load_state, save_state
from core.health import monitored_task

# =====================================================
# API ENDPOINTS
# =====================================================
API_BASE = "https://api-pro.ransomware.live/victims"
RECENT_ENDPOINT = f"{API_BASE}/recent"
SEARCH_ENDPOINT = f"{API_BASE}/search"

HEADERS = {
    "X-API-KEY": RANSOMWARELIVE_API_TOKEN,
    "Accept": "application/json",
}

# =====================================================
# NORMALIZATION (CRITICAL FIX)
# =====================================================
def normalize_victim(v: dict) -> dict:
    """
    Normalize ransomware.live victim object across endpoints.
    Matches behavior of original uploaded scripts.
    """
    return {
        "company": v.get("victim") or v.get("post_title") or "N/A",
        "group": v.get("group") or v.get("group_name") or "N/A",
        "country": v.get("country") or "N/A",
        "discovered": v.get("discovered") or "N/A",
        "url": v.get("post_url") or v.get("claim_url") or "N/A",
    }


def victim_uid(v: dict) -> str:
    n = normalize_victim(v)
    return f"{n['company']}|{n['group']}|{n['discovered']}"


# =====================================================
# FORMATTER (SPOOK SHACK THEME)
# =====================================================
def spook_victim_card(raw: dict, title: str) -> str:
    v = normalize_victim(raw)

    return (
        f"🕯️ **{title}** 🕯️\n\n"
        f"🏢 **Company:** {v['company']}\n"
        f"🌍 **Country:** {v['country']}\n"
        f"🦠 **Group:** {v['group']}\n"
        f"📅 **Discovered:** {v['discovered']}\n"
        f"🔗 **Claim URL:** {v['url']}"
    )


# =====================================================
# API HELPER
# =====================================================
async def fetch_json(url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


# =====================================================
# SCHEDULED GLOBAL FEED
# =====================================================
@tasks.loop(seconds=POLL_INTERVAL)
@monitored_task("ransomware_global")
async def ransomware_loop():
    data = await fetch_json(f"{RECENT_ENDPOINT}?order=discovered")
    if not data or "victims" not in data or not data["victims"]:
        return

    victim = data["victims"][0]
    uid = victim_uid(victim)

    state = load_state()
    if state.get("last_ransomware_uid") == uid:
        return

    channel = client.get_channel(GLOBAL_CHANNEL_ID)
    if channel:
        await channel.send(
            spook_victim_card(victim, "🌍 Global Ransomware Victim")
        )

    state["last_ransomware_uid"] = uid
    save_state(state)


# =====================================================
# MANUAL SEARCH HANDLER (RESTORED + FIXED)
# =====================================================
async def handle_victim_search(message: discord.Message) -> bool:
    if SEARCH_CHANNEL_ID and message.channel.id != SEARCH_CHANNEL_ID:
        return False

    query = message.content.strip()
    if len(query) < 3:
        await message.channel.send(
            "🕯️ **The Shack murmurs…**\n"
            "Give me at least **3 characters** to search the breach archives."
        )
        return True

    await message.channel.send(
        f"🕯️ Searching the breach archives for **{query}**…"
    )

    url = f"{SEARCH_ENDPOINT}?q={quote_plus(query)}&order=discovered"
    data = await fetch_json(url)

    if not data or "victims" not in data or not data["victims"]:
        await message.channel.send(
            "🕯️ **Nothing answered the call.**\n"
            "No ransomware victims matched that query."
        )
        return True

    # Match original behavior: show up to 5 results
    victims = data["victims"][:5]

    for v in victims:
        await message.channel.send(
            spook_victim_card(v, "🔎 Ransomware Victim Match")
        )

    return True
