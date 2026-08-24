import aiohttp
import json
from datetime import datetime, timedelta
from collections import Counter
import discord

from core.client import client
from core.config import (
    ACTOR_DOSSIER_CHANNEL_ID,
    ACTOR_DOSSIER_FORUM_ID,
    RANSOMWARELIVE_API_TOKEN,
    NVD_CVE_CHANNEL_ID,
)
from core.openai_client import openai_chat


# ======================================================
# MITRE ATT&CK FETCH
# ======================================================

MITRE_URL = "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"


async def fetch_mitre_ttps(actor):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(MITRE_URL) as resp:
                data = json.loads(await resp.text())
    except Exception:
        return []

    actor = actor.lower()
    techniques = []

    for obj in data.get("objects", []):
        if obj.get("type") == "intrusion-set" and actor in obj.get("name", "").lower():
            actor_id = obj.get("id")

            for rel in data.get("objects", []):
                if (
                    rel.get("type") == "relationship"
                    and rel.get("relationship_type") == "uses"
                    and rel.get("source_ref") == actor_id
                ):
                    target = rel.get("target_ref")

                    for t in data.get("objects", []):
                        if t.get("id") == target and t.get("type") == "attack-pattern":
                            techniques.append(t.get("name"))

    return sorted(set(techniques))


# ======================================================
# RANSOMWARE VICTIMS
# ======================================================

async def fetch_recent_actor_victims(actor):

    if not RANSOMWARELIVE_API_TOKEN:
        return []

    month = datetime.utcnow().strftime("%m")
    url = f"https://api-pro.ransomware.live/victims/?group={actor.lower()}&month={month}"

    headers = {
        "X-API-KEY": RANSOMWARELIVE_API_TOKEN,
        "Accept": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                raw = await resp.text()
                data = json.loads(raw)
    except Exception:
        return []

    if isinstance(data, dict):
        data = data.get("victims", [])

    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    results = []

    for item in data:
        discovered = item.get("discovered")
        if not discovered:
            continue

        try:
            dt = datetime.fromisoformat(discovered.replace("Z", ""))
        except Exception:
            continue

        if dt >= seven_days_ago:
            results.append({
                "victim": item.get("victim", "Unknown"),
                "industry": item.get("industry", "Unknown"),
                "country": item.get("country", "Unknown"),
            })

    return results


# ======================================================
# FETCH CVEs FROM DISCORD CHANNEL
# ======================================================

async def fetch_recent_cves():
    channel = client.get_channel(NVD_CVE_CHANNEL_ID)
    if not channel:
        return []

    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    cves = []

    async for msg in channel.history(limit=200):
        if msg.created_at.replace(tzinfo=None) < seven_days_ago:
            break

        if "CVE-" in msg.content:
            for line in msg.content.splitlines():
                if line.startswith("🆔"):
                    cves.append(line.split(":")[-1].strip())

    return cves


# ======================================================
# CVE ALIGNMENT
# ======================================================

def match_cves_to_ttps(cves, ttps):
    keywords = [
        "remote",
        "rce",
        "auth",
        "deserialization",
        "privilege",
        "exchange",
        "vpn",
        "citrix",
        "rdp",
        "fortinet",
        "apache",
    ]

    likely = []
    for cve in cves:
        for k in keywords:
            if k.lower() in cve.lower():
                likely.append(cve)

    return list(set(likely))[:10]


# ======================================================
# OPENAI PROFILE BUILDER
# ======================================================

async def build_profile(actor, industries, ttps):

    system_prompt = """
You are a senior cyber threat intelligence analyst.
Follow formatting EXACTLY.
Do NOT add extra sections.
Professional tone.
"""

    user_prompt = f"""
Actor: {actor}

Industries:
{industries}

Known TTPs:
{", ".join(ttps)}

FORMAT STRICTLY AS:

Threat Actor Operational
**Profile:** {actor}

**Overview**
Provide operational overview.

**Motivation**
Explain motivations.

**TTP Explanation**
Explain how the actor uses its techniques operationally.

**Key TTP Techniques**
- Bullet technique
- Bullet technique
"""

    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_prompt.strip()},
    ]

    return await openai_chat(messages)


# ======================================================
# MAIN HANDLER
# ======================================================

async def handle_actor_dossier(message: discord.Message):

    if message.channel.id != ACTOR_DOSSIER_CHANNEL_ID:
        return False

    if not message.content.lower().startswith("!actor"):
        return False

    parts = message.content.split()
    if len(parts) < 2:
        await message.channel.send("Usage: !actor <name>")
        return True

    actor = parts[1]

    await message.channel.send("🕯️ Gathering intelligence...")

    cves = await fetch_recent_cves()
    victims = await fetch_recent_actor_victims(actor)
    ttps = await fetch_mitre_ttps(actor)

    industry_counter = Counter(v["industry"] for v in victims)
    industries = ", ".join(
        f"{k} ({v})" for k, v in industry_counter.items()
    ) or "No dominant industry detected."

    likely_cves = match_cves_to_ttps(cves, ttps)

    profile = await build_profile(actor, industries, ttps)

    victim_block = (
        "\n".join(f"- {v['victim']} ({v['country']})" for v in victims)
        if victims else
        "No victims last 7 days."
    )

    ttp_block = (
        "\n".join(f"- {t}" for t in ttps)
        if ttps else
        "No TTPs found."
    )

    cve_block = (
        "\n".join(f"- {c}" for c in likely_cves)
        if likely_cves else
        "No CVEs aligned."
    )

    final_output = f"""
📊 Intelligence Profile
{profile}

🎯 **Recent Victims**
{victim_block}

🏭 **Industry Targeting**
{industries}

🧠 **Known TTPs**
{ttp_block}

🚨 **Latest CVE Aligned with TTPs**
{cve_block}
"""

    forum = client.get_channel(ACTOR_DOSSIER_FORUM_ID)
    thread = await forum.create_thread(
        name=f"🎭 Actor Dossier: {actor.upper()}",
        content=final_output[:1900]
    )

    t = thread.thread
    remaining = final_output[1900:]

    while remaining:
        await t.send(remaining[:1900])
        remaining = remaining[1900:]

    return True
