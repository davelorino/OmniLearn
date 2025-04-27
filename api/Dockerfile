# api/Dockerfile  – clean build for the FastAPI container
FROM python:3.12-slim

WORKDIR /app

# ---- copy source code ----
COPY core     ./core
COPY api      ./api
COPY workers  ./workers

# ---- install deps ----
RUN pip install --no-cache-dir \
        "fastapi[all]" \
        sqlmodel \
        pydantic==2.* \
        asyncpg \
        sentence-transformers \
        qdrant-client \
        "psycopg2-binary<2.9.10" \
        pypdf2 \
        "markdown-it-py[plugins]" \
        mdit-py-plugins \
        openai

# ---- launch ----
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
