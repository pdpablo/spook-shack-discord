from core.state import STATE
from core.utils import chunk_text

async def handle_health(msg):
    if msg.author.bot:
        return False
    if msg.content.strip().lower() != "!health":
        return False

    health = STATE.get("task_health", {})
    if not health:
        await msg.reply("No task health data available.")
        return

    lines = ["🩺 **Spook Shack Task Health**\n"]

    for name, h in sorted(health.items()):
        status = "🟢 OK" if "last_success" in h else "🔴 ERROR"
        running = " (running)" if h.get("running") else ""
        lines.append(
            f"**{name}** {status}{running}\n"
            f"- Last success: {h.get('last_success','—')}\n"
            f"- Last failure: {h.get('last_failure','—')}\n"
            f"- Duration: {h.get('last_duration_sec','—')}s\n"
            f"- Error: {h.get('last_error','—')}\n"
        )

    for chunk in chunk_text("\n".join(lines)):
        await msg.reply(chunk)
