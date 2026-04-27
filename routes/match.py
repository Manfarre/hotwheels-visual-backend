from fastapi import APIRouter, File, UploadFile

from services.match_service import process_match

router = APIRouter(prefix="/api", tags=["Match"])


@router.post("/match")
async def match_hotwheel(image: UploadFile = File(...)):
    return await process_match(image)
