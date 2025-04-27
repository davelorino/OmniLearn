#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  check_stack.sh  –  fast sanity-check after `docker compose up -d`
# ---------------------------------------------------------------------------
set -euo pipefail

fail() { echo "❌ $1"; exit 1; }

echo -n "FastAPI   ... "
curl -fsS http://localhost:8000/health       | grep -q '"status":"ok"' || fail "FastAPI down"
echo "ok"

echo -n "Postgres  ... "
docker compose exec -T postgres pg_isready -q                              || fail "Postgres down"
echo "ok"

echo -n "Qdrant    ... "
curl -fsS http://localhost:6333/healthz  | grep -q '"status":"ok"'         || fail "Qdrant down"
echo "ok"

echo -n "llama-cpp ... "
curl -fsS http://localhost:8001/v1/models | grep -qi 'tinyllama'           || fail "llama-cpp down / model missing"
echo "ok"

echo "All services healthy ✅"
