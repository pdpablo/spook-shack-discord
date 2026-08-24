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

    params = {"resultsPerPage": 1}
    headers = {"apiKey": NVD_API_KEY} if NVD_API_KEY else {}

    async with http.http_session.get(NVD_URL, params=params, headers=headers) as r:
        data = await r.json()

    item = data["vulnerabilities"][0]["cve"]
    cve_id = item["id"]

    if STATE.get("last_cve") == cve_id:
        return

    metrics = item.get("metrics", {})
    cvss = metrics.get("cvssMetricV31", [{}])[0].get("cvssData", {})

    msg = format_cve({
        "id": cve_id,
        "severity": f"{cvss.get('baseSeverity','N/A')} ({cvss.get('baseScore','N/A')})",
        "published": item["published"],
        "summary": item["descriptions"][0]["value"][:500],
    })

    await client.get_channel(NVD_CVE_CHANNEL_ID).send(msg)
    STATE["last_cve"] = cve_id
    save_state(STATE)
