#!/usr/bin/env bash
# -----------------------------------------------------------------------------
#  OmniLearn project bootstrap – ONE‑SHOT script
# -----------------------------------------------------------------------------
#  Usage:   bash setup.sh  [domain1 domain2 …]
#           bash setup.sh            # => stats japanese italian (defaults)
#
#  Creates a fully runnable repo in the CURRENT directory and a Docker stack
#  identical to the one you just proved working (Postgres, Qdrant 1.7.3, API,
#  vLLM with TinyLlama‑1.1B‑Chat). No manual patching afterwards.
# -----------------------------------------------------------------------------
set -euo pipefail

############################ 0  CONFIG ////////////////////////////////////////
DOMAINS=("${@:-stats japanese italian}")      # positional args or defaults
MODEL_FILE="tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
MODEL_SRC="${MODEL_SRC:-}"                    # optional env var to point to file

############################ 1  CHECK ENV /////////////////////////////////////
[[ -d .git ]] && echo "🛑  Run in an *empty* folder" && exit 1
command -v docker >/dev/null     || { echo "Docker required"; exit 1; }
command -v python3 >/dev/null    || { echo "Python 3 required"; exit 1; }

############################ 2  CREATE VENV ///////////////////////////////////
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet "fastapi[all]" asyncpg qdrant-client sqlmodel openai \
                     markdown-it-py[plugins] sentence-transformers pypdf2 jq

############################ 3  REPO TREE /////////////////////////////////////
mkdir -p core/api api/routers workers db/versions db/seeds \
         notebooks tests/e2e frontend/src/{pages,components,lib} domains \
         model-cache
cat > .gitignore <<'GI'
.venv/
__pycache__/
model-cache/*.gguf
GI

echo 'POSTGRES_PASSWORD=pass' > .env.example

############################ 4  FASTAPI SKELETON //////////////////////////////
cat > api/main.py <<'PY'
from fastapi import FastAPI
from api.routers import authoring, grading, planner, progress

app = FastAPI(title="Personal Learning OS")

app.include_router(authoring.router, prefix="/author")
app.include_router(grading.router,   prefix="/grade")
app.include_router(planner.router,   prefix="/plan")
app.include_router(progress.router,  prefix="/progress")

@app.get("/health")
async def health():
    return {"status": "ok"}
PY

ROUTER_STUB='from fastapi import APIRouter
router = APIRouter(tags=["stub"])

@router.get("/ping")
async def ping():
    return {"ping": "pong"}
'
for r in authoring grading planner progress ingest; do
  printf '%s\n' "$ROUTER_STUB" > "api/routers/${r}.py"
done

cat > api/Dockerfile <<'DOCKER'
FROM python:3.12-slim
WORKDIR /app
COPY ../core ./core
COPY . .
RUN pip install --no-cache-dir "fastapi[all]" sqlmodel pydantic==2.* \
        qdrant-client openai asyncpg markdown-it-py[plugins] \
        sentence-transformers pypdf2
CMD ["uvicorn","api.main:app","--host","0.0.0.0","--port","8000"]
DOCKER

############################ 5  DOMAIN SEEDS //////////////////////////////////
for D in "${DOMAINS[@]}"; do
  mkdir -p "domains/$D"/{trusted,items}
  printf -- "- id: %s/root\n  label: Root of %s\n  parent_id: null\n" \
          "$D" "$D" > "domains/$D/skills.yaml"
  DOMAIN_CAP=$(tr '[:lower:]' '[:upper:]' <<<"${D:0:1}")${D:1}
  printf -- "name: %s\nstreak_gate:\n  correct_in_row: 5\ndaily_time_budget: 45\n" \
          "$DOMAIN_CAP" > "domains/$D/config.yaml"
done

############################ 6  DOCKER‑COMPOSE ////////////////////////////////
cat > docker-compose.yml <<'YAML'
services:
  postgres:
    image: ankane/pgvector:latest
    environment:
      POSTGRES_PASSWORD: pass
    volumes: [pgdata_named:/var/lib/postgresql/data]
    ports: ["5432:5432"]

  qdrant:
    image: qdrant/qdrant:v1.7.3
    volumes: [qdrant_named:/qdrant/storage]
    ports: ["6333:6333"]

  vllm:
    image: ghcr.io/abetlen/llama-cpp-python:v0.2.79
    environment:
      MODEL: /models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
      USE_MLOCK: "0"
    volumes:
      - ./model-cache:/models:ro
    ports: ["8001:8000"]
    restart: unless-stopped

  api:
    build:
      context: .
      dockerfile: ./api/Dockerfile
    command: ["uvicorn","api.main:app","--host","0.0.0.0","--port","8000"]
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:pass@postgres:5432/postgres
      QDRANT_URL:  http://qdrant:6333
      OPENAI_BASE_URL: http://vllm:8000/v1
      OPENAI_API_KEY: dummy
    depends_on: [postgres, qdrant, vllm]
    ports: ["8000:8000"]

volumes:
  pgdata_named:
  qdrant_named:
YAML

############################ 7  COPY MODEL ////////////////////////////////////
if [[ -f "model-cache/$MODEL_FILE" ]]; then
   echo "✔  Model already present in ./model-cache";
elif [[ -n "$MODEL_SRC" && -f "$MODEL_SRC" ]]; then
   cp "$MODEL_SRC" "model-cache/" && echo "✔  Copied model from \$MODEL_SRC";
else
   echo "⚠️  Model $MODEL_FILE not found. Downloading (~640 MB)…";
   huggingface-cli download TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF \
       $MODEL_FILE --local-dir ./model-cache --local-dir-use-symlinks False;
fi

############################ 8  DONE //////////////////////////////////////////
echo "\n🎉  Project scaffolded. Next steps:"
echo "   1. source .venv/bin/activate"
echo "   2. docker compose up -d"
echo "   3. curl -s http://localhost:8000/health  &&  curl -s http://localhost:8001/v1/models | jq ."
