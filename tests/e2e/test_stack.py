import os, time, requests, psycopg2
import pytest
from qdrant_client import QdrantClient, exceptions as qexc

FASTAPI_URL  = os.getenv("FASTAPI_URL", "http://localhost:8000")
POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "dbname=postgres user=postgres password=pass host=localhost port=5432",
)
QDRANT_URL   = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION   = "doc_chunks"
LLM_URL      = os.getenv("LLM_URL", FASTAPI_URL.replace("8000", "8001") + "/v1")

# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------
def wait_http(url: str, timeout: int = 30):
    t0 = time.time()
    while True:
        try:
            r = requests.get(url, timeout=2)
            if r.ok:
                return r
        except requests.exceptions.ConnectionError:
            pass
        if time.time() - t0 > timeout:
            raise TimeoutError(f"{url} not up after {timeout}s")
        time.sleep(1)

# ---------- FastAPI ------------------------------------------------
def test_fastapi_health():
    r = wait_http(f"{FASTAPI_URL}/health")
    assert r.json() == {"status": "ok"}

# ---------- Postgres -----------------------------------------------
def test_postgres_tables():
    needed = {
        "user",
        "interest",
        "skillnode",
        "embedding",
        "assessmentitem",
        "attempt",
    }
    with psycopg2.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public';"
        )
        rows = {r[0] for r in cur.fetchall()}
    assert needed <= rows

# ---------- Qdrant --------------------------------------------------
def test_qdrant_health_and_collection():
    # HTTP healthz
    rh = wait_http(f"{QDRANT_URL}/healthz")
    assert rh.json()["status"] == "ok"

    # collection check via client
    qc = QdrantClient(url=QDRANT_URL, timeout=2, prefer_grpc=False)
    try:
        colls = {c.name for c in qc.get_collections().collections}
    except qexc.BaseClientException:
        pytest.fail("Qdrant client cannot list collections")
    assert COLLECTION in colls or COLLECTION == "", "doc_chunks collection missing"

# ---------- llama-cpp ----------------------------------------------
def test_llama_completion():
    payload = {
        "model": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 1,
    }
    # give the container time to load the model on cold start
    for _ in range(3):
        try:
            r = requests.post(f"{LLM_URL}/chat/completions", json=payload, timeout=15)
            r.raise_for_status()
            txt = r.json()["choices"][0]["message"]["content"].strip()
            assert txt
            return
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError):
            time.sleep(5)
    pytest.fail("llama-cpp did not respond after retries")
