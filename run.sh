#!/usr/bin/env bash
# GroundTruth one-shot runner.   ./run.sh [local|docker|test|setup]
# local  (default): create venv, install deps, migrate the DB, start API (:8000) + worker + web (:3000)
# docker          : docker compose up --build (API, worker, Postgres, web)
set -euo pipefail
cd "$(dirname "$0")"
MODE="${1:-local}"
[ -f .env ] || { cp .env.example .env; echo "Created .env from .env.example"; }

case "$MODE" in
  docker) exec docker compose up --build ;;
  setup|local|test)
    PY="${PYTHON:-python3}"; command -v "$PY" >/dev/null || PY=python
    [ -d .venv ] || "$PY" -m venv .venv
    BIN=.venv/bin; [ -d .venv/Scripts ] && BIN=.venv/Scripts
    "$BIN/python" -m pip install -q --upgrade pip
    "$BIN/python" -m pip install -q -e "packages/groundtruth[api,db,genai,dev]"
    (cd apps/web && npm ci)
    [ "$MODE" = setup ] && { echo "Setup complete."; exit 0; }
    if [ "$MODE" = test ]; then "$BIN/python" -m pytest; exit $?; fi
    if [ -z "${DATABASE_URL:-}" ] && ! grep -Eq '^\s*DATABASE_URL\s*=\s*\S+' .env 2>/dev/null; then
      echo "error: DATABASE_URL is empty in .env. Set e.g. DATABASE_URL=sqlite:///data/interim/groundtruth.db before running local mode." >&2
      exit 1
    fi
    # Migrate once, then run API and worker; without the worker a queued analysis never completes.
    "$BIN/python" -m apps.worker.main --migrate --exit-when-idle
    "$BIN/python" -m uvicorn apps.api.main:app --port 8000 &
    API=$!
    "$BIN/python" -m apps.worker.main &
    WORKER=$!; trap 'kill $API $WORKER 2>/dev/null' EXIT
    cd apps/web && NEXT_PUBLIC_API_URL=http://localhost:8000 npx next dev -p 3000 ;;
  *) echo "usage: $0 [local|docker|test|setup]"; exit 1 ;;
esac
