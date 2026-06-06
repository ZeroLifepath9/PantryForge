# Pantry Forge

What can I make with what I have? Cooking app with guest accounts, diet filters, and mock recipes until Spoonacular is enabled.

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

## Mock mode (default)

With `USE_MOCK_DATA=true` and no Spoonacular key, searches use local sample recipes.

## Project layout

- `backend/app/` — FastAPI API
- `frontend/public/` — HTML/CSS/JS (edit locally, push to GitHub, Render redeploys)
- Occult Forge is separate — untouched