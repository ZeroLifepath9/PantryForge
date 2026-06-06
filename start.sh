#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
UVICORN="${ROOT}/.venv/bin/uvicorn"
if [ ! -x "${UVICORN}" ]; then
  UVICORN="uvicorn"
fi

if [ -f "${ROOT}/app/main.py" ]; then
  export PYTHONPATH="${ROOT}"
  echo "Starting ${UVICORN} PYTHONPATH=${PYTHONPATH} PORT=${PORT:-8000}"
  exec "${UVICORN}" app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
fi

if [ -f "${ROOT}/backend/app/main.py" ]; then
  export PYTHONPATH="${ROOT}/backend"
  echo "Starting ${UVICORN} PYTHONPATH=${PYTHONPATH} PORT=${PORT:-8000}"
  exec "${UVICORN}" app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
fi

echo "DEPLOY ERROR: no app/main.py found"
exit 1