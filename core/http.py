import aiohttp
import ssl
import socket
import asyncio

TOR_SOCKS = "socks5h://127.0.0.1:9050"
http_session: aiohttp.ClientSession | None = None

async def init_http():
    global http_session
    connector = aiohttp.TCPConnector(
        family=socket.AF_INET,
        ssl=ssl.create_default_context()
    )
    http_session = aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=30)
    )

async def wait_for_http():
    while http_session is None:
        await asyncio.sleep(0.5)
