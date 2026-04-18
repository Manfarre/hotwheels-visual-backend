from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
from difflib import SequenceMatcher

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
        "keywords": ["BATMOBILE", "BATMAOBILE", "BATMAN", "181/250", "2021", "FOR LIFE", "DC"],
        "type": "Mainline",
        "rarity": "Media",
        "priceRange": "$100 - $260 MXN",
    },
    {
        "name": "Volkswagen Beetle",
        "keywords": ["VOLKSWAGEN BEETLE", "BEETLE", "CHECKMATE", "8/9", "VOLKSWAGEN", "VW BEETLE"],
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
    text = text.upper()
    for ch in [",", ".", ":", ";", "-", "_", "(", ")", "[", "]", "'", '"']:
        text = text.replace(ch, " ")
    text = text.replace("/", " / ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()

def tokenize(text: str):
    return [t for t in normalize_text(text).split(" ") if t.strip()]

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def keyword_score(keyword: str, normalized_text: str, tokens: list[str]) -> float:
    keyword = normalize_text(keyword)

    if keyword in normalized_text:
        return 1.0

    keyword_parts = [p for p in keyword.split(" ") if p.strip()]
    if not keyword_parts:
        return 0.0

    best_part_scores = []
    for part in keyword_parts:
        part_best = 0.0
        for token in tokens:
            score = similarity(part, token)
            if score > part_best:
                part_best = score
        best_part_scores.append(part_best)

    avg_score = sum(best_part_scores) / len(best_part_scores)
    if avg_score >= 0.84:
        return avg_score
    return 0.0

def find_best_match(ocr_text: str):
    normalized = normalize_text(ocr_text)
    tokens = tokenize(ocr_text)

    best_item = None
    best_score = 0.0
    best_debug = {}

    for item in CATALOG:
        total_score = 0.0
        matched_keywords = []

        for keyword in item["keywords"]:
            score = keyword_score(keyword, normalized, tokens)
            if score > 0:
                total_score += score
                matched_keywords.append((keyword, round(score, 2)))

        if total_score > best_score:
            best_score = total_score
            best_item = item
            best_debug = {
                "matched_keywords": matched_keywords,
                "total_score": round(total_score, 2)
            }

    return best_item, best_score, normalized, best_debug

def average_rgb(img: Image.Image):
    small = img.resize((80, 80))
    pixels = list(small.getdata())
    total = len(pixels)

    r = sum(p[0] for p in pixels) / total
    g = sum(p[1] for p in pixels) / total
    b = sum(p[2] for p in pixels) / total
    return r, g, b

def color_ratio(img: Image.Image, predicate):
    small = img.resize((100, 100))
    pixels = list(small.getdata())
    if not pixels:
        return 0.0
    count = sum(1 for p in pixels if predicate(p[0], p[1], p[2]))
    return count / len(pixels)

def visual_fallback(img: Image.Image):
    width, height = img.size

    top_half = img.crop((0, 0, width, int(height * 0.55)))
    center_band = img.crop((int(width * 0.15), int(height * 0.15), int(width * 0.85), int(height * 0.60)))

    blue_ratio_top = color_ratio(
        top_half,
        lambda r, g, b: b > 110 and b > r + 20 and b > g + 10
    )
    dark_ratio_top = color_ratio(
        top_half,
        lambda r, g, b: r < 70 and g < 70 and b < 90
    )
    red_ratio_top = color_ratio(
        top_half,
        lambda r, g, b: r > 120 and r > g + 25 and r > b + 25
    )
    yellow_ratio_top = color_ratio(
        top_half,
        lambda r, g, b: r > 150 and g > 120 and b < 120
    )

    dark_ratio_center = color_ratio(
        center_band,
        lambda r, g, b: r < 95 and g < 95 and b < 95
    )
    blue_ratio_center = color_ratio(
        center_band,
        lambda r, g, b: b > 100 and b > r + 15 and b > g + 10
    )

    # Batmobile DC/Batman style card:
    # mucho azul + bastante negro + centro oscuro/azulado
    if blue_ratio_top >= 0.22 and dark_ratio_top >= 0.18 and (dark_ratio_center >= 0.20 or blue_ratio_center >= 0.18):
        return {
            "name": "Batmobile",
            "similarity": 0.66,
            "type": "Mainline",
            "rarity": "Media",
            "priceRange": "$100 - $260 MXN",
            "debug": {
                "reason": "fallback_visual_batmobile",
                "blue_ratio_top": round(blue_ratio_top, 2),
                "dark_ratio_top": round(dark_ratio_top, 2),
                "dark_ratio_center": round(dark_ratio_center, 2),
                "blue_ratio_center": round(blue_ratio_center, 2),
            }
        }

    # Beetle card genérico: azul fuerte + acentos rojos/amarillos
    if blue_ratio_top >= 0.24 and (red_ratio_top >= 0.12 or yellow_ratio_top >= 0.10):
        return {
            "name": "Volkswagen Beetle",
            "similarity": 0.58,
            "type": "Mainline",
            "rarity": "Media",
            "priceRange": "$100 - $220 MXN",
            "debug": {
                "reason": "fallback_visual_beetle",
                "blue_ratio_top": round(blue_ratio_top, 2),
                "red_ratio_top": round(red_ratio_top, 2),
                "yellow_ratio_top": round(yellow_ratio_top, 2),
            }
        }

    return None

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

        best_item, best_score, normalized_text, debug = find_best_match(ocr_text)

        if best_item and best_score >= 1.0:
            similarity_value = min(0.55 + (best_score * 0.08), 0.98)

            top_match = {
                "name": best_item["name"],
                "similarity": round(similarity_value, 2),
                "type": best_item["type"],
                "rarity": best_item["rarity"],
                "priceRange": best_item["priceRange"],
            }

            return {
                "topMatch": top_match,
                "matches": [top_match],
                "message": (
                    f"Match por OCR backend. "
                    f"Imagen: {width}x{height}. "
                    f"Score: {round(best_score, 2)}. "
                    f"Keywords: {debug.get('matched_keywords', [])}. "
                    f"Texto: {normalized_text}"
                )
            }

        fallback = visual_fallback(img)
        if fallback:
            top_match = {
                "name": fallback["name"],
                "similarity": fallback["similarity"],
                "type": fallback["type"],
                "rarity": fallback["rarity"],
                "priceRange": fallback["priceRange"],
            }

            return {
                "topMatch": top_match,
                "matches": [top_match],
                "message": (
                    f"Match por fallback visual. "
                    f"Imagen: {width}x{height}. "
                    f"Debug: {fallback['debug']}. "
                    f"Texto OCR: {normalized_text}"
                )
            }

        return {
            "topMatch": None,
            "matches": [],
            "message": (
                f"No hubo coincidencia en backend. "
                f"Imagen: {width}x{height}. "
                f"Score OCR: {round(best_score, 2)}. "
                f"Texto: {normalized_text}"
            )
        }

    except Exception as e:
        return {
            "topMatch": None,
            "matches": [],
            "message": f"Error procesando imagen: {str(e)}"
        }
