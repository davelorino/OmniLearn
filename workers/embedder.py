"""
workers/embedder.py
– No network calls at import time.
– Lazy SentenceTransformer + lazy Qdrant client.
"""
from __future__ import annotations

import os, pathlib, uuid, re
from typing import Iterable, List

import markdown_it
from mdit_py_plugins.front_matter import front_matter_plugin
from sqlmodel import Session

from core.db import engine
from core.models import Embedding

# ── Markdown parser (cheap) ─────────────────────────────────────────────────
md = markdown_it.MarkdownIt("commonmark").use(front_matter_plugin)

# ── config ──────────────────────────────────────────────────────────────────
CHUNK_SIZE = 512
COLLECTION = "doc_chunks"
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384  # MiniLM-L6-v2 output size, avoids touching the model for dim

# ── lazy global singletons ─────────────────────────────────────────────────
_model = None
_qdrant = None


def _get_model():
    global _model
    if _model is None:
        # honour HF_HUB_OFFLINE=1 if you want fully offline containers
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBED_MODEL_NAME)
    return _model


def _get_qdrant():
    global _qdrant
    if _qdrant is None:
        from qdrant_client import QdrantClient, models, http

        _qdrant = QdrantClient(host="qdrant", port=6333, prefer_grpc=False, timeout=2.0)
        try:
            _qdrant.get_collection(COLLECTION)
        except http.exceptions.ResponseHandlingException:
            _qdrant.recreate_collection(
                COLLECTION,
                vectors_config=models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE),
            )
    return _qdrant


# ── helpers ─────────────────────────────────────────────────────────────────
def _chunks(text: str) -> Iterable[str]:
    text = re.sub(r"\s+", " ", text).strip()
    for i in range(0, len(text), CHUNK_SIZE):
        yield text[i : i + CHUNK_SIZE]


# ── public API – called by /ingest/{slug} ───────────────────────────────────
def ingest_file(path: pathlib.Path, slug: str) -> None:
    """Reads one file, chunks → embeds → stores."""
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
    else:
        text = md.render(path.read_text(encoding="utf-8"))

    vectors: List[list[float]] = []
    embeds: List[Embedding] = []
    payloads: List[dict] = []

    model = _get_model()

    for chunk in _chunks(text):
        vec = model.encode(chunk).tolist()
        cid = str(uuid.uuid4())

        embeds.append(
            Embedding(
                id=cid,
                object_type="doc_chunk",
                object_id=f"{slug}:{path.name}",
                vector=b"",  # raw vector only in Qdrant
                dim=len(vec),
            )
        )
        vectors.append(vec)
        payloads.append({"text": chunk, "source": path.name, "domain": slug})

    with Session(engine) as s:
        s.add_all(embeds)
        s.commit()

    _get_qdrant().upload_collection(
        collection_name=COLLECTION,
        vectors=vectors,
        payload=payloads,
        ids=[e.id for e in embeds],
    )
