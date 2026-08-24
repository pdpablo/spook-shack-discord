from discord.ext import tasks
from core.client import client
from core.config import NVD_CVE_CHANNEL_ID, NVD_API_KEY, POLL_INTERVAL
from core.state import STATE, save_state
from core.health import monitored_task
import core.http as http

NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def format_cve(cve):
    return (
        f"🛑 New CVE Published\n\n"
        f"🆔 CVE: {cve['id']}\n"
        f"⚠️ Severity: {cve['severity']}\n"
        f"📅 Published: {cve['published']}\n"
        f"📝 Summary: {cve['summary']}\n"
        f"🔗 NVD: https://nvd.nist.gov/vuln/detail/{cve['id']}"
    )


@tasks.loop(seconds=POLL_INTERVAL)
@monitored_task("latest_cve")
async def cve_loop():
    await http.wait_for_http()

    if not NVD_CVE_CHANNEL_ID:
        return

    params = {"resultsPerPage": 5}
    headers = {"apiKey": NVD_API_KEY} if NVD_API_KEY else {}

    async with http.http_session.get(NVD_URL, params=params, headers=headers) as r:
        data = await r.json()

    vulnerabilities = data.get("vulnerabilities", [])
    if not vulnerabilities:
        return

    last_cve = STATE.get("last_cve")
    newest_id = vulnerabilities[0]["cve"]["id"]

    pending = []
    for entry in vulnerabilities:
        item = entry.get("cve", {})
        cve_id = item.get("id")
        if not cve_id:
            continue
        if cve_id == last_cve:
            break
        pending.append(item)

    if not pending:
        return

    channel = client.get_channel(NVD_CVE_CHANNEL_ID)
    if not channel:
        return

    for item in reversed(pending):
        metrics = item.get("metrics", {})
        cvss = metrics.get("cvssMetricV31", [{}])[0].get("cvssData", {})
        msg = format_cve({
            "id": item["id"],
            "severity": f"{cvss.get('baseSeverity','N/A')} ({cvss.get('baseScore','N/A')})",
            "published": item.get("published", "N/A"),
            "summary": item.get("descriptions", [{}])[0].get("value", "No summary")[:500],
        })
        await channel.send(msg)

    STATE["last_cve"] = newest_id
    save_state(STATE)
