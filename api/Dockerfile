FROM python:3.12-slim
WORKDIR /app
COPY ../core ./core
COPY . .
RUN pip install --no-cache-dir "fastapi[all]" sqlmodel pydantic==2.* \
        qdrant-client openai asyncpg markdown-it-py[plugins] \
        sentence-transformers pypdf2
CMD ["uvicorn","api.main:app","--host","0.0.0.0","--port","8000"]
