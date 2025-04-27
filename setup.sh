#!/usr/bin/env bash
# -----------------------------------------------------------------------------
#  OmniLearn bootstrap  –  2025-04-28
#  Creates a fully runnable “Personal Learning OS” stack in the current folder
# -----------------------------------------------------------------------------
set -euo pipefail

DOMAINS=("${@:-stats}")                    # seed domain(s)
MODEL_FILE="tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"

# 1  prerequisites ------------------------------------------------------------
[[ -d .git ]] && { echo "🛑  Run in an empty dir"; exit 1; }
command -v docker >/dev/null  || { echo "Docker required"; exit 1; }
command -v python3 >/dev/null || { echo "Python 3 required"; exit 1; }

# 2  python venv --------------------------------------------------------------
python3 -m venv .venv
source .venv/bin/activate
pip install -qU pip
pip install -q "fastapi[all]" sqlmodel pydantic \
              asyncpg "psycopg[binary]>=3.1,<4" \
              sentence-transformers qdrant-client \
              "markdown-it-py[plugins]" mdit-py-plugins \
              pypdf uvicorn[standard]==0.27.1

# 3  repo tree ---------------------------------------------------------------
mkdir -p core/api api/routers workers domains model-cache
echo -e ".venv/\n__pycache__/\nmodel-cache/*.gguf" > .gitignore

# 4  FastAPI skeleton ---------------------------------------------------------
cat > api/main.py <<'PY'
from fastapi import FastAPI
from api.routers import ingest
app = FastAPI(title="Personal Learning OS")
app.include_router(ingest.router, prefix="/ingest")
@app.get("/health")
async def health(): return {"status": "ok"}
PY

cat > api/routers/ingest.py <<'PY'
from fastapi import APIRouter, BackgroundTasks, HTTPException
from workers.embedder import ingest_file
import pathlib
router = APIRouter(tags=["ingest"])
@router.post("/{slug}")
async def ingest_slug(slug: str, tasks: BackgroundTasks):
    d = pathlib.Path("domains") / slug / "trusted"
    if not d.exists(): raise HTTPException(404, "domain not found")
    files = list(d.glob("*"))
    if not files: raise HTTPException(400, "no files")
    for f in files: tasks.add_task(ingest_file, f, slug)
    return {"queued": len(files)}
PY

# 5  lazy embedder ------------------------------------------------------------
cat > workers/__init__.py <<'PY'
import re, uuid, pathlib
from typing import Iterable, List
import markdown_it, mdit_py_plugins.front_matter
from sqlmodel import Session
from core.db import engine
from core.models import Embedding

CHUNK=512; COLL="doc_chunks"; DIM=384
md = markdown_it.MarkdownIt("commonmark").use(
        mdit_py_plugins.front_matter.front_matter_plugin)

_model = _q = None
def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model
def _get_qdrant():
    global _q
    if _q is None:
        from qdrant_client import QdrantClient, http, models
        _q = QdrantClient(host="qdrant", port=6333, prefer_grpc=False, timeout=2)
        try: _q.get_collection(COLL)
        except http.exceptions.ResponseHandlingException:
            _q.recreate_collection(
                COLL,
                vectors_config=models.VectorParams(size=DIM,
                                                   distance=models.Distance.COSINE))
    return _q
def _chunks(t:str)->Iterable[str]:
    t = re.sub(r"\s+"," ",t).strip()
    for i in range(0,len(t),CHUNK): yield t[i:i+CHUNK]
def ingest_file(path:pathlib.Path, slug:str)->None:
    if path.suffix.lower()==".pdf":
        from pypdf import PdfReader
        text="\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    else:
        text = md.render(path.read_text(encoding="utf-8"))
    vecs:List[List[float]]=[]; embeds=[]; payload=[]
    for chunk in _chunks(text):
        vec=_get_model().encode(chunk).tolist()
        cid=str(uuid.uuid4())
        embeds.append(Embedding(id=cid,object_type="doc_chunk",
                    object_id=f"{slug}:{path.name}",vector=b"",dim=len(vec)))
        vecs.append(vec)
        payload.append({"text":chunk,"source":path.name,"domain":slug})
    with Session(engine) as s: s.add_all(embeds); s.commit()
    _get_qdrant().upload_collection(collection_name=COLL,
                                    vectors=vecs,payload=payload,
                                    ids=[e.id for e in embeds])
PY

# 6  minimal core models & db -----------------------------------------------
cat > core/db.py <<'PY'
import os
from sqlmodel import create_engine, SQLModel
DATABASE_URL=os.getenv("DATABASE_URL",
  "postgresql+psycopg://postgres:pass@localhost:5432/postgres")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
def init_db():
    import core.models  # noqa
    SQLModel.metadata.create_all(engine)
PY

cat > core/models.py <<'PY'
from datetime import datetime
from sqlmodel import SQLModel, Field
def _id():
    import uuid; return str(uuid.uuid4())
class Embedding(SQLModel, table=True):
    id:str         = Field(default_factory=_id, primary_key=True)
    object_type:str
    object_id:str
    vector:bytes
    dim:int
    created_at:datetime = Field(default_factory=datetime.utcnow)
PY

# 7  API Dockerfile -----------------------------------------------------------
cat > api/Dockerfile <<'DOCKER'
FROM python:3.12-slim
WORKDIR /app
COPY core     ./core
COPY api      ./api
COPY workers  ./workers
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
 && pip install --no-cache-dir fastapi[all] sqlmodel pydantic asyncpg \
      "psycopg[binary]>=3.1,<4" sentence-transformers qdrant-client \
      pypdf2 "markdown-it-py[plugins]" mdit-py-plugins openai \
      uvicorn[standard]==0.27.1 \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
CMD ["uvicorn","api.main:app","--host","0.0.0.0","--port","8000"]
DOCKER

# 8  docker-compose -----------------------------------------------------------
ARCH=$(uname -m); QTAG="qdrant/qdrant:v1.7.3"
[[ $ARCH == arm64 ]] && QTAG="qdrant/qdrant:v1.7.3-arm64"

cat > docker-compose.yml <<YAML
services:
  postgres:
    image: ankane/pgvector:latest
    environment: { POSTGRES_PASSWORD: pass }
    volumes: [pgdata_named:/var/lib/postgresql/data]
    ports: ["5432:5432"]

  qdrant:
    image: $QTAG
    volumes: [qdrant_named:/qdrant/storage]
    ports: ["6333:6333"]

  vllm:
    image: ghcr.io/abetlen/llama-cpp-python:v0.2.79
    environment:
      MODEL: /models/$MODEL_FILE
      USE_MLOCK: "0"
    volumes: [./model-cache:/models:ro]
    ports: ["8001:8000"]
    restart: unless-stopped

  api:
    build: { context: ., dockerfile: ./api/Dockerfile }
    command: ["uvicorn","api.main:app","--host","0.0.0.0","--port","8000"]
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:pass@postgres:5432/postgres
      QDRANT_URL:  http://qdrant:6333
    depends_on: [postgres, qdrant, vllm]
    ports: ["8000:8000"]
    volumes:
      - ./workers:/app/workers:ro
      - ./api:/app/api:ro
      - ./domains:/app/domains:ro

volumes:
  pgdata_named:
  qdrant_named:
YAML

# 9  seed domains -------------------------------------------------------------
for d in "${DOMAINS[@]}"; do
  mkdir -p "domains/$d"/{trusted,items}
  echo "- id: $d/root\n  label: Root of $d\n  parent_id: null" \
       > "domains/$d/skills.yaml"
done

echo -e "\n🎉  Scaffold ready."
echo "1)  source .venv/bin/activate"
echo "2)  docker compose up -d --build"
echo "3)  curl -s http://localhost:8000/health"
