# api/Dockerfile  – clean build for the FastAPI container
FROM python:3.12-slim

WORKDIR /app

# ---- copy source code ----
COPY core     ./core
COPY api      ./api
COPY workers  ./workers

# ---- install deps ----
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
&& pip install --no-cache-dir \
        fastapi[all] \
        sqlmodel \
        "pydantic==2.*" \
        asyncpg \
        "psycopg[binary]>=3.1,<4" \
        sentence-transformers \
        qdrant-client \
        pypdf2 \
        "markdown-it-py[plugins]" \
        mdit-py-plugins \
        openai \
        # --- pin uvicorn so script & module match ---
        "uvicorn[standard]==0.27.1" \
&& apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- launch ----
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
