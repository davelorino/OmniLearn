from fastapi import FastAPI
from api.routers import authoring, grading, planner, progress

app = FastAPI(title="Personal Learning OS")

app.include_router(authoring.router, prefix="/author")
app.include_router(grading.router,   prefix="/grade")
app.include_router(planner.router,   prefix="/plan")
app.include_router(progress.router,  prefix="/progress")

@app.get("/health")
async def health():
    return {"status": "ok"}
