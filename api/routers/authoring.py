from fastapi import APIRouter
router = APIRouter(tags=["stub"])

@router.get("/ping")
async def ping():
    return {"ping": "pong"}

