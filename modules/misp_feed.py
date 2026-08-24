from discord.ext import tasks
from core.client import client
from core.config import (
    MISP_FEED_URL,
    CHANNEL_RANSOMWARE,
    CHANNEL_VULNERABILITY,
    CHANNEL_APT,
    CHANNEL_GENERAL,
    POLL_INTERVAL,
)
from core.state import STATE, save_state
from core.health import monitored_task
import core.http as http


def select_channel(tags):
    tags = " ".join(t.lower() for t in tags)

    if "ransomware" in tags:
        return CHANNEL_RANSOMWARE
    if "vulnerability" in tags or "cve" in tags:
        return CHANNEL_VULNERABILITY
    if "apt" in tags or "malware" in tags:
        return CHANNEL_APT
    return CHANNEL_GENERAL


@tasks.loop(seconds=POLL_INTERVAL)
@monitored_task("threatcluster_misp")
async def poll_misp():
    await http.wait_for_http()

    async with http.http_session.get(MISP_FEED_URL) as r:
        manifest = await r.json()

    seen = set(STATE.get("misp_seen", []))

    for event_id, event in manifest.items():
        if event_id in seen:
            continue

        info = event.get("info", "No description")
        tags = [t.get("name", "") for t in event.get("Tag", [])]
        channel_id = select_channel(tags)

        channel = client.get_channel(channel_id)
        if not channel:
            continue

        message = (
            f"🕵️ **ThreatCluster Intelligence**\n\n"
            f"🆔 Event ID: {event_id}\n"
            f"📝 Info: {info}\n"
            f"🏷️ Tags: {', '.join(tags) if tags else 'None'}"
        )

        await channel.send(message)
        seen.add(event_id)

    STATE["misp_seen"] = list(seen)
    save_state(STATE)
