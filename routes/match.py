from fastapi import APIRouter, File, Form, UploadFile

from app.services.match_service import process_match

router = APIRouter()


@router.post("/match")
async def match_hotwheel(
    image: UploadFile = File(...),
    ocr_text: str = Form("")
):
    image_bytes = await image.read()
    return process_match(image_bytes=image_bytes, client_ocr=ocr_text)
