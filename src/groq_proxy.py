import time
from itertools import cycle

import httpx
from fastapi import FastAPI, Request, Response, HTTPException

from config import GroqProxyConfig

GROQ_BASE_URL = GroqProxyConfig.BASE_URL.value
COOLDOWN_SECONDS = GroqProxyConfig.KEY_COOLDOWN_SECONDS.value
GROQ_API_KEYS = GroqProxyConfig.API_KEYS.value

if not GROQ_API_KEYS:
    raise RuntimeError("GROQ_API_KEYS must contain at least one key")

app = FastAPI()
key_cycle = cycle(GROQ_API_KEYS)
key_cooldowns: dict[str, float] = {}


def available_keys() -> list[str]:
    now = time.time()
    first = next(key_cycle)
    ordered = [first] + [key for key in GROQ_API_KEYS if key != first]

    return [
        key for key in ordered
        if key_cooldowns.get(key, 0) <= now
    ]


def mark_rate_limited(api_key: str) -> None:
    key_cooldowns[api_key] = time.time() + COOLDOWN_SECONDS


@app.get("/v1/models")
async def list_models():
    keys = available_keys()
    if not keys:
        raise HTTPException(status_code=429, detail="All Groq API keys are cooling down")

    async with httpx.AsyncClient(timeout=30) as client:
        for api_key in keys:
            res = await client.get(
                f"{GROQ_BASE_URL}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )

            if res.status_code in (429, 503):
                mark_rate_limited(api_key)
                continue

            return Response(
                content=res.content,
                status_code=res.status_code,
                media_type=res.headers.get("content-type", "application/json"),
            )

    raise HTTPException(status_code=429, detail="All Groq API keys failed")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.body()
    keys = available_keys()

    if not keys:
        raise HTTPException(status_code=429, detail="All Groq API keys are cooling down")

    async with httpx.AsyncClient(timeout=None) as client:
        last_response = None

        for api_key in keys:
            res = await client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                content=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )

            last_response = res

            if res.status_code in (429, 503):
                mark_rate_limited(api_key)
                continue

            return Response(
                content=res.content,
                status_code=res.status_code,
                media_type=res.headers.get("content-type", "application/json"),
            )

    return Response(
        content=last_response.content if last_response else b'{"error":"No Groq response"}',
        status_code=429,
        media_type="application/json",
    )
