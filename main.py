from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CATALOG = [
    {
        "name": "Batmobile",
        "keywords": ["BATMOBILE", "BATMAOBILE", "BATMAN", "181/250", "2021"],
        "type": "Mainline",
        "rarity": "Media",
        "priceRange": "$100 - $260 MXN",
    },
    {
        "name": "Volkswagen Beetle",
        "keywords": ["VOLKSWAGEN BEETLE", "BEETLE", "CHECKMATE", "8/9", "VOLKSWAGEN"],
        "type": "Mainline",
        "rarity": "Media",
        "priceRange": "$100 - $220 MXN",
    },
    {
        "name": "Volkswagen Drag Bus",
        "keywords": ["DRAG BUS", "VOLKSWAGEN DRAG BUS", "DRAG", "BUS"],
        "type": "Especial",
        "rarity": "Alta",
        "priceRange": "$1200 - $3500 MXN",
    },
]

def normalize_text(text: str) -> str:
    return (
        text.upper()
        .replace(",", " ")
        .replace(".", " ")
        .replace(":", " ")
        .replace(";", " ")
        .replace("-", " ")
        .replace("_", " ")
        .replace("/", " / ")
        .replace("  ", " ")
        .strip()
    )

def find_best_match(ocr_text: str):
    normalized = normalize_text(ocr_text)
    best_item = None
    best_score = 0

    for item in CATALOG:
        score = 0
        for keyword in item["keywords"]:
            if keyword in normalized:
                score += 1

        if score > best_score:
            best_score = score
            best_item = item

    return best_item, best_score, normalized

@app.get("/")
def root():
    return {"message": "Hot Wheels visual backend activo"}

@app.post("/match")
async def match_hotwheel(
    image: UploadFile = File(...),
    ocr_text: str = Form("")
):
    contents = await image.read()

    try:
        img = Image.open(io.BytesIO(contents)).convert("RGB")
        width, height = img.size

        best_item, best_score, normalized_text = find_best_match(ocr_text)

        if best_item and best_score > 0:
            similarity = min(0.55 + (best_score * 0.12), 0.98)

            top_match = {
                "name": best_item["name"],
                "similarity": round(similarity, 2),
                "type": best_item["type"],
                "rarity": best_item["rarity"],
                "priceRange": best_item["priceRange"],
            }

            return {
                "topMatch": top_match,
                "matches": [top_match],
                "message": f"Match por OCR backend. Imagen: {width}x{height}. Texto: {normalized_text}"
            }

        return {
            "topMatch": None,
            "matches": [],
            "message": f"No hubo coincidencia en backend. Imagen: {width}x{height}. Texto: {normalized_text}"
        }

    except Exception as e:
        return {
            "topMatch": None,
            "matches": [],
            "message": f"Error procesando imagen: {str(e)}"
        }
