# AlchemyPantry

What are we working with? Cooking app with guest accounts, diet filters, AI meal advisor (xAI), and mock recipes until Spoonacular is enabled.

## Local dev (Windows)

```powershell
cd C:\Users\natur\pantry-forge\backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 — try guest login, then search: `2 eggs, tomato, basil`

## Deploy to Render

1. Push this repo to GitHub (e.g. `ZeroLifepath9/PantryForge`)
2. Render → **New Web Service** → connect the repo
3. Build: `pip install -r requirements.txt`
4. Start: `bash start.sh`
5. Health check path: `/healthz`
6. Environment variables:
   - `ENV` = `production`
   - `JWT_SECRET` = 32+ random chars (Secret type)
   - `USE_MOCK_DATA` = `true` (mock recipes; no Spoonacular quota used)
   - Optional later: `SPOONACULAR_API_KEY`, `XAI_API_KEY`

Or apply [`render.yaml`](render.yaml) as a Blueprint.

## AI meal advisor (xAI)

After each search, **Kitchen advisor** suggests mains, sides, salads, dips, and upgrade tips (e.g. brined vs raw meat) based on your ingredients, restrictions, and "What sounds good?".

- **Without `XAI_API_KEY`:** rule-based guidance (still useful for testing).
- **With `XAI_API_KEY`:** full Grok-powered insights via `POST /advisor/insights`.

Check status: `GET /advisor/status` or `/healthz` (`xai_configured` field).

### Enable xAI on Render

1. Render Dashboard → your service → **Environment**
2. Add `XAI_API_KEY` = your key from https://console.x.ai (Secret type)
3. Optional: `XAI_MODEL` override (default `grok-3-mini-fast` in code)
4. **Manual Deploy** → verify `/healthz` shows `"xai_configured": true`
5. Search with ingredients → advisor badge should say **AI advisor** (not Guidance mode)

Local: add `XAI_API_KEY=...` to `backend/.env` and restart uvicorn.

## Mock mode (default)

With `USE_MOCK_DATA=true` and no Spoonacular key, searches use local sample recipes.

## Project layout

- `backend/app/` — FastAPI API
- `frontend/public/` — HTML/CSS/JS (edit locally, push to GitHub, Render redeploys)
- Occult Forge is separate — untouched