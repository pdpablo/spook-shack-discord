import aiohttp
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_BASE_URL = "https://api.openai.com/v1/chat/completions"


async def openai_chat(
    messages: list,
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
    max_tokens: int = 400,
):
    """
    Async OpenAI chat helper.
    Matches behavior of original inline OpenAI calls.
    """

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    timeout = aiohttp.ClientTimeout(total=45)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            OPENAI_BASE_URL, headers=headers, json=payload
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(
                    f"OpenAI API error {resp.status}: {text}"
                )

            data = await resp.json()
            return data["choices"][0]["message"]["content"].strip()
