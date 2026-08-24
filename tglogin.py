from telethon import TelegramClient
import os
from dotenv import load_dotenv

load_dotenv()

TG_API_ID = int(os.getenv("TG_API_ID"))
TG_API_HASH = os.getenv("TG_API_HASH")

with TelegramClient("tg_session", TG_API_ID, TG_API_HASH) as client:
    print("✅ Telegram login successful. Session saved.")

