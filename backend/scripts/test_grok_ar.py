import asyncio

from app.services.grok_recipes import search_craving_lineup


async def main():
    payload, mock = await search_craving_lineup("street tacos")
    print("mock", mock, "live", payload.get("live"))
    print(payload.get("message"))
    for r in payload.get("recipes") or []:
        print("-", r["title"], "|", r.get("source_url", "")[:50])
        print("  ing:", len(r.get("ingredient_names") or []), "steps:", len(r.get("instructions") or []))


asyncio.run(main())