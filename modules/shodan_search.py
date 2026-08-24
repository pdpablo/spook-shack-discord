import aiohttp
import discord

from core.config import SHODAN_API_KEY, SHODAN_SEARCH_CHANNEL_ID
import core.http as http
from core.utils import chunk_text

SHODAN_BASE = "https://api.shodan.io"


def _fmt_hosts(hostnames):
    if not hostnames:
        return "N/A"
    return ", ".join(hostnames[:3])


def _fmt_vulns(vulns):
    if not vulns:
        return "None"
    if isinstance(vulns, dict):
        vulns = list(vulns.keys())
    return ", ".join(list(vulns)[:5])


def _fmt_location(item):
    bits = [item.get("city"), item.get("region_code"), item.get("country_name")]
    return ", ".join(b for b in bits if b) or "Unknown"


def _fmt_match(item):
    ip = item.get("ip_str") or item.get("ip") or "unknown-ip"
    port = item.get("port", "?")
    transport = item.get("transport", "tcp")
    org = item.get("org") or item.get("isp") or "Unknown org"
    product = item.get("product") or item.get("title") or item.get("data", "")
    if isinstance(product, str):
        product = product.splitlines()[0] if product else ""
    else:
        product = ""
    if not product:
        product = "N/A"
    hostnames = _fmt_hosts(item.get("hostnames", []))
    location = _fmt_location(item)
    vulns = _fmt_vulns(item.get("vulns"))
    return f"""• `{ip}:{port}/{transport}`
  Org: {org}
  Hostnames: {hostnames}
  Location: {location}
  Product: {product}
  Vulns: {vulns}"""


async def _shodan_request(path: str, params: dict | None = None):
    await http.wait_for_http()
    if not SHODAN_API_KEY:
        raise RuntimeError("SHODAN_API_KEY is not set")

    query = dict(params or {})
    query["key"] = SHODAN_API_KEY

    timeout = aiohttp.ClientTimeout(total=30)
    async with http.http_session.get(f"{SHODAN_BASE}{path}", params=query, timeout=timeout) as resp:
        data = await resp.json(content_type=None)
        if resp.status != 200:
            detail = data.get("error") if isinstance(data, dict) else await resp.text()
            raise RuntimeError(f"Shodan API error {resp.status}: {detail}")
        return data


def _usage() -> str:
    return """🛰️ **Shodan Search Commands**
`!shodan <query>` — search hosts
`!shodan count <query>` — count matching hosts without consuming search results
`!shodan info` — show API membership / plan info"""


async def handle_shodan(message: discord.Message) -> bool:
    if message.author.bot:
        return False

    if message.channel.id != SHODAN_SEARCH_CHANNEL_ID:
        return False

    content = message.content.strip()
    if not content.lower().startswith("!shodan"):
        return False

    if not SHODAN_API_KEY:
        await message.channel.send("🛰️ SHODAN_API_KEY is not configured.")
        return True

    parts = content.split(maxsplit=2)
    if len(parts) == 1:
        await message.channel.send(_usage())
        return True

    action = parts[1].lower()

    try:
        if action in {"help", "?"}:
            await message.channel.send(_usage())
            return True

        if action == "info":
            data = await _shodan_request("/api-info")
            msg = f"""🛰️ **Shodan Membership Info**
Plan: `{data.get('plan', 'unknown')}`
Query credits: `{data.get('query_credits', 'unknown')}`
Scan credits: `{data.get('scan_credits', 'unknown')}`
Unlocked: `{data.get('unlocked', 'unknown')}`
Monitored IPs: `{data.get('monitored_ips', 'unknown')}`"""
            await message.channel.send(msg)
            return True

        if action == "count":
            if len(parts) < 3:
                await message.channel.send("🛰️ Usage: `!shodan count <query>`")
                return True
            query = parts[2].strip()
            data = await _shodan_request("/shodan/host/count", {"query": query})
            facets = data.get("facets")
            facet_line = ""
            newline = chr(10)
            if facets:
                facet_line = newline + newline.join(f"- {k}: {v}" for k, v in list(facets.items())[:5])
            await message.channel.send(
                f"""🛰️ **Shodan Count**
Query: `{query}`
Total: **{data.get('total', 0)}**{facet_line}"""
            )
            return True

        query = content[len("!shodan"):].strip()
        if not query:
            await message.channel.send(_usage())
            return True

        data = await _shodan_request("/shodan/host/search", {"query": query, "page": 1})
        matches = data.get("matches", [])[:5]
        total = data.get("total", 0)

        if not matches:
            await message.channel.send(f"🛰️ No Shodan matches for `{query}`.")
            return True

        lines = [
            "🛰️ **Shodan Results**",
            f"Query: `{query}`",
            f"Total matches: **{total}**",
            "",
        ]
        for idx, item in enumerate(matches, start=1):
            lines.append(f"**Result {idx}**")
            lines.append(_fmt_match(item))
            lines.append("")

        for chunk in chunk_text(chr(10).join(lines).rstrip()):
            await message.channel.send(chunk)
        return True

    except Exception as exc:
        await message.channel.send(f"🛰️ Shodan lookup failed: `{exc}`")
        return True
