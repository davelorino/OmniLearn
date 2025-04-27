# workers/embedder.py
"""
Lazy embedder + Qdrant uploader
– no network work at import-time
– handles .md / .pdf, chunks text, stores metadata in Postgres,
  vectors in Qdrant.
"""

from __future__ import annotations

import pathlib, re, uuid
from typing import Iterable, List

import markdown_it
import mdit_py_plugins.front_matter
from sqlmodel import Session

from core.db import engine
from core.models import Embedding

# --------------------------------------------------------------------------- #
# Configuration constants
# --------------------------------------------------------------------------- #
COLLECTION = "doc_chunks"          # single source of truth
DIM        = 384
CHUNK      = 512                   # characters per chunk

# --------------------------------------------------------------------------- #
# Lazy singletons (avoid import-time downloads / network)
# --------------------------------------------------------------------------- #
_md = markdown_it.MarkdownIt("commonmark").use(
    mdit_py_plugins.front_matter.front_matter_plugin
)

_model = None
_qdrant = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("/models/all-MiniLM-L6-v2")
    return _model


def _get_qdrant():
    """Return a live Qdrant client and create collection if missing."""
    global _qdrant
    if _qdrant is None:
        from qdrant_client import QdrantClient, http, models   # already there ✔
        from qdrant_client.http.exceptions import UnexpectedResponse
        _qdrant = QdrantClient(
            host="qdrant",
            port=6333,
            prefer_grpc=False,
            timeout=2,
            check_compatibility=False,        # ← add this line
        )
        try:
            _qdrant.get_collection(COLLECTION)
        except UnexpectedResponse:                                
            _qdrant.recreate_collection(
                COLLECTION,
                vectors_config=models.VectorParams(
                    size=DIM, distance=models.Distance.COSINE
                ),
            )
    return _qdrant


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _chunks(text: str) -> Iterable[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    for i in range(0, len(clean), CHUNK):
        yield clean[i : i + CHUNK]


# --------------------------------------------------------------------------- #
# Public ingestion function (called from FastAPI background task)
# --------------------------------------------------------------------------- #
def ingest_file(path: pathlib.Path, slug: str) -> None:
    """Read file, chunk, embed, store rows & vectors."""
    # -------- read & extract text --------
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        text = "\n".join(
            page.extract_text() or "" for page in PdfReader(str(path)).pages
        )
    else:
        text = _md.render(path.read_text(encoding="utf-8"))

    # -------- chunk & embed --------
    vecs: List[List[float]] = []
    embeds: List[Embedding] = []
    payloads = []

    for chunk in _chunks(text):
        vec = _get_model().encode(chunk).tolist()
        eid = str(uuid.uuid4())

        embeds.append(
            Embedding(
                id=eid,
                object_type="doc_chunk",
                object_id=f"{slug}:{path.name}",
                vector=b"",  # pgvector column not used in this demo
                dim=len(vec),
            )
        )
        vecs.append(vec)
        payloads.append(
            {"text": chunk, "source": path.name, "domain": slug}
        )

    # -------- write metadata in Postgres --------
    with Session(engine) as s:
        s.add_all(embeds)
        s.commit()
        ids = [e.id for e in embeds]          # grab ids while still bound

    # -------- upload vectors + payloads to Qdrant --------
    _get_qdrant().upload_collection(
        collection_name=COLLECTION,
        vectors=vecs,
        payload=payloads,
        ids=ids,
    )
