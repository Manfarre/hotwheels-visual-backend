from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
import re
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
        "keywords": {
            "BATMOBILE": 1.0,
            "BATMAOBILE": 0.95,
            "BATMAN": 0.65,
            "DC": 0.45,
            "181/250": 0.45,
            "181": 0.20,
            "2021": 0.15,
            "FOR LIFE": 0.40,
        },
        "negative_keywords": ["VOLKSWAGEN", "BEETLE", "DRAG BUS"],
        "type": "Mainline",
        "rarity": "Media",
        "priceRange": "$100 - $260 MXN",
    },
    {
        "name": "Volkswagen Beetle",
        "keywords": {
            "VOLKSWAGEN BEETLE": 1.0,
            "VW BEETLE": 0.95,
            "BEETLE": 0.70,
            "VOLKSWAGEN": 0.55,
            "CHECKMATE": 0.55,
            "8/9": 0.35,
        },
        "negative_keywords": ["BATMAN", "BATMOBILE", "DRAG BUS"],
        "type": "Mainline",
        "rarity": "Media",
        "priceRange": "$100 - $220 MXN",
    },
    {
        "name": "Volkswagen Drag Bus",
        "keywords": {
            "VOLKSWAGEN DRAG BUS": 1.0,
            "DRAG BUS": 0.95,
            "VW DRAG BUS": 0.95,
            "BUS": 0.30,
            "DRAG": 0.30,
        },
        "negative_keywords": ["BATMAN", "BATMOBILE", "BEETLE"],
        "type": "Especial",
        "rarity": "Alta",
        "priceRange": "$1200 - $3500 MXN",
    },
]

NOISE_WORDS = {
    "HOT", "WHEELS", "MATTEL", "COM", "EXCLUSNE", "EXCLUSIVE", "GUARANTEED",
    "METAL", "METALFLAKE", "COLLECTOR", "SERIES", "HW", "NEW", "MODEL",
    "MADE", "MALAYSIA", "THAILAND", "INDONESIA", "WARNING", "AGES",
}

def normalize_text(text: str) -> str:
    text = text.upper()
    replacements = {
        "0": "O",
        "1": "I",
        "5": "S",
        "8": "B",
        "|": "I",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    for ch in [",", ".", ":", ";", "-", "_", "(", ")", "[", "]", "'", '"', "!", "?"]:
        text = text.replace(ch, " ")
    text = text.replace("/", " / ")
    text = re.sub(r"\s+", " ", text).strip()
    return text

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

    if not best_part_scores:
        return 0.0

    avg_score = sum(best_part_scores) / len(best_part_scores)

    if len(keyword_parts) >= 2:
        if avg_score >= 0.84:
            return avg_score
    else:
        if avg_score >= 0.90:
            return avg_score

    return 0.0

def compute_text_quality(tokens: list[str]) -> float:
    if not tokens:
        return 0.0

    useful = 0
    for t in tokens:
        if len(t) >= 3 and t not in NOISE_WORDS:
            useful += 1

    quality = useful / max(len(tokens), 1)
    return round(quality, 3)

def find_all_matches(ocr_text: str):
    normalized = normalize_text(ocr_text)
    tokens = tokenize(ocr_text)
    text_quality = compute_text_quality(tokens)

    results = []

    for item in CATALOG:
        total_score = 0.0
        matched_keywords = []
        penalties = []

        for keyword, weight in item["keywords"].items():
            score = keyword_score(keyword, normalized, tokens)
            if score > 0:
                weighted = score * weight
                total_score += weighted
                matched_keywords.append((keyword, round(weighted, 2)))

        for neg in item.get("negative_keywords", []):
            neg_norm = normalize_text(neg)
            if neg_norm in normalized:
                total_score -= 0.45
                penalties.append(neg)

        if text_quality < 0.15:
            total_score *= 0.75
        elif text_quality < 0.25:
            total_score *= 0.88

        results.append({
            "item": item,
            "score": round(total_score, 3),
            "matched_keywords": matched_keywords,
            "penalties": penalties,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results, normalized, text_quality

def color_ratio(img: Image.Image, predicate):
    small = img.resize((100, 100))
    pixels = list(small.getdata())
    if not pixels:
        return 0.0
    count = sum(1 for p in pixels if predicate(p[0], p[1], p[2]))
    return count / len(pixels)

def visual_fallback(img: Image.Image, text_quality: float):
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

    # Solo usar fallback visual si el texto es pobre
    if text_quality > 0.22:
        return None

    if blue_ratio_top >= 0.22 and dark_ratio_top >= 0.18 and (dark_ratio_center >= 0.20 or blue_ratio_center >= 0.18):
        return {
            "name": "Batmobile",
            "similarity": 0.64,
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

    if blue_ratio_top >= 0.24 and (red_ratio_top >= 0.12 or yellow_ratio_top >= 0.10):
        return {
            "name": "Volkswagen Beetle",
            "similarity": 0.57,
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

def build_match_payload(item, similarity_value):
    return {
        "name": item["name"],
        "similarity": round(similarity_value, 2),
        "type": item["type"],
        "rarity": item["rarity"],
        "priceRange": item["priceRange"],
    }

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

        ranked, normalized_text, text_quality = find_all_matches(ocr_text)
        best = ranked[0] if ranked else None
        second = ranked[1] if len(ranked) > 1 else None

        top_matches = []
        for r in ranked[:3]:
            if r["score"] > 0:
                similarity_value = min(0.50 + (r["score"] * 0.10), 0.97)
                top_matches.append(build_match_payload(r["item"], similarity_value))

        if best and best["score"] >= 0.95:
            margin_ok = (second is None) or ((best["score"] - second["score"]) >= 0.18)

            if margin_ok:
                similarity_value = min(0.55 + (best["score"] * 0.09), 0.98)
                top_match = build_match_payload(best["item"], similarity_value)

                return {
                    "topMatch": top_match,
                    "matches": top_matches,
                    "message": (
                        f"Match por OCR backend. "
                        f"Imagen: {width}x{height}. "
                        f"Score: {round(best['score'], 2)}. "
                        f"TextQuality: {text_quality}. "
                        f"Keywords: {best.get('matched_keywords', [])}. "
                        f"Penalties: {best.get('penalties', [])}. "
                        f"Texto: {normalized_text}"
                    )
                }

        fallback = visual_fallback(img, text_quality)
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
                    f"TextQuality: {text_quality}. "
                    f"Debug: {fallback['debug']}. "
                    f"Texto OCR: {normalized_text}"
                )
            }

        return {
            "topMatch": None,
            "matches": top_matches,
            "message": (
                f"No hubo coincidencia confiable. "
                f"Imagen: {width}x{height}. "
                f"BestScore: {round(best['score'], 2) if best else 0}. "
                f"TextQuality: {text_quality}. "
                f"Texto: {normalized_text}"
            )
        }

    except Exception as e:
        return {
            "topMatch": None,
            "matches": [],
            "message": f"Error procesando imagen: {str(e)}"
        }
