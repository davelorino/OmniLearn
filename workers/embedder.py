# workers/embedder.py
from __future__ import annotations
import pathlib, uuid, re
from typing import Iterable

import markdown_it
from mdit_py_plugins.front_matter import front_matter_plugin 
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient, models
from sqlmodel import Session
from core.db import engine
from core.models import Embedding

EMBED_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
md = markdown_it.MarkdownIt("commonmark").use(front_matter_plugin)

CHUNK_SIZE = 512  # characters; tweak later
COLLECTION = "doc_chunks"

qdrant = QdrantClient("localhost", port=6333)
qdrant.recreate_collection(
    COLLECTION,
    vectors_config=models.VectorParams(size=EMBED_MODEL.get_sentence_embedding_dimension(), distance=models.Distance.COSINE),
)

def _text_chunks(text: str) -> Iterable[str]:
    text = re.sub(r"\s+", " ", text).strip()
    for i in range(0, len(text), CHUNK_SIZE):
        yield text[i : i + CHUNK_SIZE]

def ingest_file(path: pathlib.Path, slug: str) -> None:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
    else:  # assume Markdown / plain text
        text = md.render(path.read_text(encoding="utf-8"))

    embeds = []
    vectors = []
    payloads = []

    for chunk in _text_chunks(text):
        vec = EMBED_MODEL.encode(chunk).tolist()
        chunk_id = str(uuid.uuid4())

        embeds.append(
            Embedding(
                id=chunk_id,
                object_type="doc_chunk",
                object_id=f"{slug}:{path.name}",
                vector=b"",  # we don't store the raw vector in Postgres, only in Qdrant
                dim=len(vec),
            )
        )
        vectors.append(vec)
        payloads.append({"text": chunk, "source": str(path.name), "domain": slug})

    # --- Postgres ---
    with Session(engine) as s:
        s.add_all(embeds)
        s.commit()

    # --- Qdrant ---
    qdrant.upload_collection(
        collection_name=COLLECTION,
        vectors=vectors,
        payload=payloads,
        ids=[e.id for e in embeds],
    )
