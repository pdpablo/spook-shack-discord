from datetime import datetime, timezone
import asyncio

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def defang(text: str):
    return text.replace(".", "[.]") if text else "N/A"

def chunk_text(text: str, limit=1900):
    if len(text) <= limit:
        return [text]
    out, buf = [], ""
    for line in text.splitlines():
        if len(buf) + len(line) + 1 > limit:
            out.append(buf)
            buf = line
        else:
            buf += ("\n" if buf else "") + line
    if buf:
        out.append(buf)
    return out

async def safe_send(dest, text: str):
    for chunk in chunk_text(text):
        await dest.send(chunk)
        await asyncio.sleep(0.4)
