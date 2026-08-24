import socket
from typing import Optional
from urllib.parse import urlparse
from datetime import timezone

import discord

from core.client import client
from core.config import (
    TAKEDOWN_COMMAND_CHANNEL_ID,
    TAKEDOWN_FORUM_CHANNEL_ID,
    ORG_NAME,
    ORG_CONTACT_EMAIL,
)
from core.utils import now_utc, defang, chunk_text
from core.http import http_session

# ----------------------------
# Helpers copied from original
# ----------------------------

def normalize_domain(d: str) -> str:
    d = d.strip().lower()
    d = d.replace("http://", "").replace("https://", "")
    return d.split("/")[0]


def is_valid_domain(d: str) -> bool:
    return "." in d and " " not in d


async def dns_lookup(domain: str):
    results = {"a": [], "aaaa": [], "ns": [], "cname": []}

    try:
        infos = socket.getaddrinfo(domain, None)
        for info in infos:
            if info[0] == socket.AF_INET:
                results["a"].append(info[4][0])
            elif info[0] == socket.AF_INET6:
                results["aaaa"].append(info[4][0])
    except Exception:
        pass

    async def doh(qtype: str):
        try:
            async with http_session.get(
                "https://dns.google/resolve",
                params={"name": domain, "type": qtype},
            ) as r:
                if r.status != 200:
                    return []
                data = await r.json()
                return [a["data"].rstrip(".") for a in data.get("Answer", []) if "data" in a]
        except Exception:
            return []

    results["ns"] = await doh("NS")
    results["cname"] = await doh("CNAME")

    for k in results:
        results[k] = sorted(set(results[k]))

    return results


def detect_provider_from_dns(ns, cname):
    hints = []
    blob = " ".join(ns + cname).lower()

    if "cloudflare" in blob:
        hints.append("Cloudflare (likely proxy/CDN)")
    if "github.io" in blob:
        hints.append("GitHub Pages")
    if "netlify" in blob:
        hints.append("Netlify")
    if "vercel" in blob:
        hints.append("Vercel")
    if "firebase" in blob or "web.app" in blob:
        hints.append("Google Firebase Hosting")
    if "azurewebsites" in blob:
        hints.append("Azure App Service")
    if "amazonaws" in blob:
        hints.append("AWS (CloudFront / EC2 / S3)")

    return hints


def takedown_thread_title(malicious: str, legit: str) -> str:
    return f"🕯️ Exorcism Request: {malicious} (impersonating {legit})"


def takedown_report_body(malicious: str, legit: str, hints: list[str]) -> str:
    hint_line = ", ".join(hints) if hints else "Unknown (needs manual confirmation)"
    return (
        f"👻 **Spook Shack Takedown Dossier**\n"
        f"🕯️ **Filed:** {now_utc()}\n\n"
        f"**Suspected malicious domain:** `{defang(malicious)}`\n"
        f"**Impersonated domain:** `{defang(legit)}`\n\n"
        f"🧠 **Likely platform hints:** {hint_line}\n\n"
        f"🧾 A ready-to-send report template is posted below in this thread.\n"
        f"⚠️ Reminder: Always verify the domain is malicious before submitting abuse reports."
    )


def build_email_template(malicious, legit, dns):
    return (
        "📨 **Ready-to-send Abuse Report**\n\n"
        "**Subject:** Phishing / Brand Impersonation — Takedown Request\n\n"
        f"**From:** {ORG_NAME} Security Team <{ORG_CONTACT_EMAIL}>\n\n"
        "Hello Abuse Team,\n\n"
        "We are reporting a domain involved in phishing and brand impersonation.\n\n"
        f"**Impersonated brand:** {legit}\n"
        f"**Malicious domain:** {malicious}\n\n"
        "**Technical indicators:**\n"
        f"- A: {', '.join(dns.get('a', [])) or 'N/A'}\n"
        f"- AAAA: {', '.join(dns.get('aaaa', [])) or 'N/A'}\n"
        f"- NS: {', '.join(dns.get('ns', [])) or 'N/A'}\n"
        f"- CNAME: {', '.join(dns.get('cname', [])) or 'N/A'}\n\n"
        "Please investigate under your AUP and take appropriate action.\n\n"
        f"{ORG_NAME} Security Team\n"
        f"{ORG_CONTACT_EMAIL}"
    )


# ----------------------------
# Dispatcher-compatible handler
# ----------------------------

async def handle_takedown(message) -> bool:
    if message.author.bot:
        return False

    if message.channel.id != TAKEDOWN_COMMAND_CHANNEL_ID:
        return False

    if not message.content.lower().startswith("!takedown"):
        return False

    parts = message.content.split()
    if len(parts) < 3:
        await message.channel.send(
            "🕯️ Usage: `!takedown <malicious-domain> <legit-domain>`\n"
            "Example: `!takedown fake-spook-shack.com spook-shack.com`"
        )
        return True

    malicious = normalize_domain(parts[1])
    legit = normalize_domain(parts[2])

    if not is_valid_domain(malicious) or not is_valid_domain(legit):
        await message.channel.send("🧟 Invalid domain format.")
        return True

    await message.channel.send(
        f"🕯️ Summoning an exorcism dossier for `{defang(malicious)}`…"
    )

    forum = client.get_channel(TAKEDOWN_FORUM_CHANNEL_ID)
    if not isinstance(forum, discord.ForumChannel):
        await message.channel.send("❌ Takedown forum misconfigured.")
        return True

    dns = await dns_lookup(malicious)
    hints = detect_provider_from_dns(dns["ns"], dns["cname"])

    thread = await forum.create_thread(
        name=takedown_thread_title(malicious, legit),
        content=takedown_report_body(malicious, legit, hints),
    )
    t = thread.thread

    await t.send(
        "🔎 **Technical Snapshot**\n"
        f"- **A:** {', '.join(dns['a']) or 'N/A'}\n"
        f"- **AAAA:** {', '.join(dns['aaaa']) or 'N/A'}\n"
        f"- **NS:** {', '.join(dns['ns']) or 'N/A'}\n"
        f"- **CNAME:** {', '.join(dns['cname']) or 'N/A'}"
    )

    email = build_email_template(malicious, legit, dns)
    for chunk in chunk_text(email):
        await t.send(chunk)

    await t.send(
        "🧾 **Evidence Checklist**\n"
        "- Screenshot of impersonation page\n"
        "- URLs (defanged)\n"
        "- Timestamp (UTC)\n"
        "- Notes on copied branding\n\n"
        "🕯️ Verify before you banish."
    )

    await message.channel.send(f"✅ Exorcism dossier created: {t.mention}")
    return True
