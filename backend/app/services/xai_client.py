"""xAI API client (OpenAI-compatible chat completions)."""

from __future__ import annotations

import httpx

from app.config import settings


async def chat_completion(
    *,
    system: str,
    user_content: str,
    model: str | None = None,
    temperature: float = 0.5,
) -> str:
    if not settings.xai_api_key:
        raise ValueError("XAI_API_KEY is not configured")

    model = model or settings.xai_model
    url = f"{settings.xai_base_url.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.xai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                "temperature": temperature,
                "store": False,
            },
        )
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("xAI returned no choices")
    return choices[0]["message"]["content"].strip()