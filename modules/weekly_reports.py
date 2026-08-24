from datetime import timedelta, datetime, timezone
from discord import TextChannel, ForumChannel
from openai import AsyncOpenAI

from core.client import client
from core.config import (
    REPORT_COMMAND_CHANNEL_ID,
    REPORT_FORUM_CHANNEL_ID,
    OPENAI_API_KEY,
)
from core.utils import chunk_text, now_utc

ai = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def handle_weekly_report(message) -> bool:
    if message.author.bot:
        return False

    if REPORT_COMMAND_CHANNEL_ID and message.channel.id != REPORT_COMMAND_CHANNEL_ID:
        return False

    if not message.content.lower().startswith("!weeklyreport"):
        return False

    if len(message.channel_mentions) != 1:
        await message.reply("Usage: `!weeklyreport #channel`")
        return True

    target = message.channel_mentions[0]
    if not isinstance(target, TextChannel):
        await message.reply("Please mention a text channel.")
        return True

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)

    posts = []
    async for m in target.history(after=start):
        if m.author.bot and m.content:
            posts.append(m.content)

    if not posts:
        await message.reply("No bot-generated posts found in the last 7 days.")
        return True

    prompt = (
        "Summarize the following threat intelligence posts.\n"
        "Tone: executive summary, concise, actionable.\n\n"
        + "\n\n".join(posts)
    )

    resp = await ai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    summary = resp.choices[0].message.content.strip()

    forum = client.get_channel(REPORT_FORUM_CHANNEL_ID)
    if not isinstance(forum, ForumChannel):
        await message.reply("Report forum is not configured correctly.")
        return True

    title = f"📜 Weekly Intelligence Report ({start.date()} → {end.date()})"
    thread = await forum.create_thread(name=title, content=summary[:1900])
    t = thread.thread

    for chunk in chunk_text(summary[1900:]):
        await t.send(chunk)

    await t.send(
        f"\n🕯️ Generated: {now_utc()}\n"
        f"Source channel: #{target.name}\n"
        f"Bot-generated posts only"
    )

    await message.reply(f"✅ Weekly report created: {t.mention}")
    return True
