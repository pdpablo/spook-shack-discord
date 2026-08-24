import asyncio

from core.client import client
from core.config import DISCORD_BOT_TOKEN
from core.http import init_http
from core.database import db_init

# =====================================================
# discord.ext.tasks.loop JOBS
# =====================================================
from modules.rss_discussions import (
    paranormal_loop,
    lounge_loop,
    run_paranormal_once,
)
from modules.pastebin_dork_watch import (
    paste_dork_monitor,
    handle_paste_dork,
)
from modules.shodan_search import handle_shodan

from modules.ransomware_live import (
    ransomware_loop,
    handle_victim_search,
)

from modules.nvd_cve import cve_loop
from modules.misp_feed import poll_misp
from modules.hibp_haunt import haunt_monitor, start_haunt_monitor, handle_haunt

# =====================================================
# PLAIN ASYNC BACKGROUND RUNNERS
# =====================================================
from modules.nginx_creepy_crawlies import creepy_crawlies_loop

# =====================================================
# COMMAND HANDLERS
# =====================================================
from modules.takedown_request import handle_takedown
from modules.weekly_reports import handle_weekly_report
from modules.actor_dossier import handle_actor_dossier
from modules.health_command import handle_health

# =====================================================
# ASYNC RUNNERS (NON-discord TASKS)
# =====================================================
async def creepy_runner():
    while True:
        try:
            await creepy_crawlies_loop()
        except Exception as e:
            print(f"[Creepy] Error: {e}", flush=True)
        await asyncio.sleep(6 * 60 * 60)  # every 6 hours



# =====================================================
# READY EVENT
# =====================================================
@client.event
async def on_ready():
    await init_http()
    db_init()

    def safe_start(task):
        if hasattr(task, "is_running") and not task.is_running():
            task.start()

    # One-time startup behavior
    await run_paranormal_once()

    # Scheduled discord tasks
    safe_start(poll_misp)
    safe_start(paranormal_loop)
    safe_start(lounge_loop)
    safe_start(ransomware_loop)
    safe_start(cve_loop)
    safe_start(haunt_monitor)
    safe_start(paste_dork_monitor)

    # Start HIBP background
    start_haunt_monitor()

    # Plain asyncio background loops
    if not hasattr(client, "_creepy_task"):
        client._creepy_task = asyncio.create_task(creepy_runner())

    print("🕯️ Spook Shack online — all systems stable", flush=True)


# =====================================================
# MESSAGE DISPATCHER
# =====================================================
@client.event
async def on_message(message):
    if message.author.bot:
        return

    # --- Health ---
    if await handle_health(message):
        return

    # --- Actor Dossier ---
    if await handle_actor_dossier(message):
        return

    # --- Pastebin watch / quick search ---
    if await handle_paste_dork(message):
        return

    # --- Shodan search ---
    if await handle_shodan(message):
        return

    # --- Ransomware victim search ---
    if await handle_victim_search(message):
        return

    # --- Takedown request ---
    if await handle_takedown(message):
        return

    # --- Weekly reports ---
    if await handle_weekly_report(message):
        return

    # --- HIBP haunt commands ---
    if await handle_haunt(message):
        return


# =====================================================
# START BOT
# =====================================================
if __name__ == "__main__":
    client.run(DISCORD_BOT_TOKEN)
