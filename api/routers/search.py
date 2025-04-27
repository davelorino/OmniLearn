# api/routers/search.py
from typing import List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from workers.embedder import _get_model, _get_qdrant, COLLECTION, DIM
from qdrant_client import models

router = APIRouter(tags=["search"])


class Chunk(BaseModel):
    id: str
    text: str
    source: str = Field(..., description="File the chunk originated from")
    score: float


@router.get("/", response_model=List[Chunk])
def search(
    q: str = Query(..., min_length=2, description="User query"),
    slug: str = Query(..., min_length=1, description="Domain slug, e.g. 'stats'"),
    k: int = Query(5, ge=1, le=50, description="Number of hits to return"),
):
    """
    Vector-search `k` nearest chunks within a single domain (`slug`).
    """
    model = _get_model()
    qdrant = _get_qdrant()

    # --- embed the query ----------------------------------------------------
    vec = model.encode(q).tolist()

    # --- filter by domain ---------------------------------------------------
    flt = models.Filter(
        must=[
            models.FieldCondition(
                key="domain",                      # payload key used in ingest
                match=models.MatchValue(value=slug),
            )
        ]
    )

    # --- search -------------------------------------------------------------
    try:
        res = qdrant.search(
            collection_name=COLLECTION,
            query_vector=vec,
            limit=k,
            with_payload=True,
            query_filter=flt,
        )
    except Exception as e:  # any Qdrant error
        raise HTTPException(500, f"search failed: {e}") from e

    # --- map to response model ---------------------------------------------
    hits: List[Chunk] = []
    for p in res:
        payload = p.payload or {}
        hits.append(
            Chunk(
                id=str(p.id),
                text=payload.get("text", ""),
                source=payload.get("source", ""),
                score=p.score,
            )
        )
    return hits
