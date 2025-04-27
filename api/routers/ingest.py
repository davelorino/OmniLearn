# api/routers/ingest.py
from fastapi import APIRouter, BackgroundTasks, HTTPException
import pathlib
from workers.embedder import ingest_file

router = APIRouter(tags=["ingest"])

@router.post("/{slug}")
async def ingest_slug(slug: str, tasks: BackgroundTasks):
    domain_dir = pathlib.Path("domains") / slug / "trusted"
    if not domain_dir.exists():
        raise HTTPException(status_code=404, detail="domain not found")

    files = list(domain_dir.glob("*"))
    if not files:
        raise HTTPException(status_code=400, detail="no files to ingest")

    for f in files:
        tasks.add_task(ingest_file, f, slug)

    return {"queued": len(files)}
