import io

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from routes.ebay_auth import router as ebay_auth_router
from services.match_service import find_best_wiki_match, visual_signals
from utils.response_builders import build_match_response

app = FastAPI(title="Hot Wheels Visual Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ebay_auth_router)


@app.get("/")
def root():
    return {"message": "Hot Wheels visual backend general activo"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/match")
async def match_hotwheel(
    image: UploadFile = File(...),
    ocr_text: str = Form("")
):
    try:
        contents = await image.read()
        img = Image.open(io.BytesIO(contents)).convert("RGB")
        width, height = img.size

        wiki_result = find_best_wiki_match(ocr_text)

        if wiki_result.get("topMatch") is not None:
            visual = visual_signals(img)
            backend_message = wiki_result.get("message", "").strip()

            final_message = (
                f"{backend_message}\n\n"
                f"Imagen: {width}x{height}\n"
                f"Señales visuales generales: {visual}"
            ).strip()

            return build_match_response(
                top_match=wiki_result.get("topMatch"),
                matches=wiki_result.get("matches", []),
                message=final_message
            )

        visual = visual_signals(img)
        fallback_message = (
            f"{wiki_result.get('message', 'Sin match online.')}\n\n"
            f"Imagen: {width}x{height}\n"
            f"Señales visuales generales: {visual}"
        ).strip()

        return build_match_response(
            top_match=None,
            matches=[],
            message=fallback_message
        )

    except Exception as e:
        return build_match_response(
            top_match=None,
            matches=[],
            message=f"Error procesando imagen: {str(e)}"
        )
