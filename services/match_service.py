import re
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any, Dict, List

from PIL import Image

from services.ebay_search_service import search_ebay_items


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.upper()
    text = text.replace("\n", " ")
    for ch in [",", ".", ":", ";", "_", "(", ")", "[", "]", "{", "}", "'", '"', "|", "•", "·"]:
        text = text.replace(ch, " ")
    text = text.replace("/", " / ")
    text = text.replace("-", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def color_ratio(img: Image.Image, predicate) -> float:
    small = img.resize((100, 100))
    pixels = list(small.getdata())
    if not pixels:
        return 0.0
    count = sum(1 for p in pixels if predicate(p[0], p[1], p[2]))
    return count / len(pixels)


def visual_signals(img: Image.Image) -> Dict[str, float]:
    width, height = img.size

    top_half = img.crop((0, 0, width, int(height * 0.55)))
    center_band = img.crop(
        (int(width * 0.10), int(height * 0.10), int(width * 0.90), int(height * 0.70))
    )

    red_ratio = color_ratio(
        top_half,
        lambda r, g, b: r > 140 and r > g + 35 and r > b + 35
    )
    blue_ratio = color_ratio(
        center_band,
        lambda r, g, b: b > 110 and b > r + 15 and b > g + 15
    )
    yellow_ratio = color_ratio(
        top_half,
        lambda r, g, b: r > 150 and g > 120 and b < 130
    )
    dark_ratio = color_ratio(
        center_band,
        lambda r, g, b: r < 75 and g < 75 and b < 75
    )

    return {
        "redRatio": round(red_ratio, 3),
        "blueRatio": round(blue_ratio, 3),
        "yellowRatio": round(yellow_ratio, 3),
        "darkRatio": round(dark_ratio, 3),
    }


def extract_ocr_text(img: Image.Image) -> str:
    try:
        import pytesseract
        text = pytesseract.image_to_string(img)
        return text or ""
    except Exception:
        return ""


def extract_years(text: str) -> List[str]:
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
    out = []
    seen = set()
    for y in years:
        if y not in seen:
            seen.add(y)
            out.append(y)
    return out


def clean_tokens_from_ocr(ocr_text: str) -> List[str]:
    text = normalize_text(ocr_text)

    tokens = re.findall(r"[A-Z0-9']{2,}", text)

    blocked = {
        "HOT", "WHEELS", "MATTEL", "WARNING", "AGES", "OVER", "NEW",
        "MODEL", "DIECAST", "METAL", "PLASTIC", "MADE", "IN", "THAILAND",
        "MALAYSIA", "INDONESIA", "CHINA", "COLLECTOR", "COLLECTORS",
        "SERIES", "ASSORTMENT", "ITEM", "TOY", "TOYS", "CAR", "CARS",
        "THE", "AND", "WITH", "FOR", "NOT", "USE", "ONLY", "FROM",
        "THIS", "THAT", "WWW", "HTTP", "HTTPS", "COM", "INC"
    }

    useful: List[str] = []
    seen = set()

    for token in tokens:
        if token in blocked:
            continue
        if len(token) < 3:
            continue
        if token.isdigit():
            continue
        if re.fullmatch(r"[0-9/]+", token):
            continue
        if token not in seen:
            seen.add(token)
            useful.append(token)

    return useful


def infer_model_phrase(ocr_text: str) -> str:
    text = normalize_text(ocr_text)
    if not text:
        return ""

    words = clean_tokens_from_ocr(text)

    if not words:
        return ""

    candidates = []
    for size in [4, 3, 2]:
        for i in range(len(words) - size + 1):
            phrase = " ".join(words[i:i + size])
            if len(phrase.replace(" ", "")) >= 6:
                candidates.append(phrase)

    preferred_terms = {
        "CAMARO", "MUSTANG", "CHEVY", "FORD", "BATMOBILE", "BEETLE",
        "BOMB", "BUS", "DRAG", "SHAKER", "VOLKSWAGEN", "COBRA",
        "CORVETTE", "DODGE", "CHARGER", "CHALLENGER", "PORSCHE",
        "NISSAN", "HONDA", "TOYOTA", "TESLA"
    }

    for phrase in candidates:
        if any(term in phrase for term in preferred_terms):
            return phrase

    return candidates[0] if candidates else ""


def build_query_from_ocr(ocr_text: str) -> str:
    text = normalize_text(ocr_text)

    if not text:
        return "hot wheels"

    years = extract_years(text)
    useful_tokens = clean_tokens_from_ocr(text)
    phrase = infer_model_phrase(text)

    parts: List[str] = ["hot wheels"]

    if phrase:
        parts.append(phrase)
    else:
        parts.extend(useful_tokens[:4])

    if years:
        parts.append(years[0])

    query = " ".join(parts).strip()
    return query if query else "hot wheels"


def score_item_against_query(item: Dict[str, Any], query: str, ocr_text: str) -> float:
    title = item.get("title", "")
    title_n = normalize_text(title)
    query_n = normalize_text(query)
    ocr_n = normalize_text(ocr_text)

    score = 0.0
    score += similarity(title_n, query_n) * 2.5

    if ocr_n:
        score += similarity(title_n, ocr_n) * 1.2

    for token in clean_tokens_from_ocr(ocr_text)[:8]:
        if token in title_n:
            score += 0.4

    for year in extract_years(ocr_text):
        if year in title_n:
            score += 0.8

    return round(score, 4)


def choose_top_match(items: List[Dict[str, Any]], query: str, ocr_text: str) -> Dict[str, Any] | None:
    if not items:
        return None

    scored = []
    for item in items:
        s = score_item_against_query(item, query, ocr_text)
        scored.append((item, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    best_item, best_score = scored[0]

    similarity_value = max(0.30, min(0.98, 0.35 + (best_score / 4.0)))

    return {
        "name": best_item.get("title", ""),
        "price": best_item.get("price", ""),
        "url": best_item.get("itemWebUrl", ""),
        "image": best_item.get("image", ""),
        "condition": best_item.get("condition", ""),
        "similarity": round(similarity_value, 2),
        "score": best_score,
    }


async def process_match(file) -> Dict[str, Any]:
    content = await file.read()

    try:
        img = Image.open(BytesIO(content)).convert("RGB")
    except Exception as e:
        return {
            "success": False,
            "topMatch": None,
            "matches": [],
            "message": f"No se pudo procesar la imagen: {str(e)}",
            "visualSignals": {},
        }

    width, height = img.size
    visual = visual_signals(img)
    ocr_text = extract_ocr_text(img)
    query = build_query_from_ocr(ocr_text)

    ebay_result = search_ebay_items(query=query, limit=8)

    if not ebay_result.get("success"):
        return {
            "success": False,
            "topMatch": None,
            "matches": [],
            "message": ebay_result.get("message", "Falló la búsqueda en eBay"),
            "queryUsed": query,
            "ocrText": ocr_text[:700],
            "cleanTokens": clean_tokens_from_ocr(ocr_text),
            "imageInfo": {
                "width": width,
                "height": height,
                "filename": getattr(file, "filename", ""),
                "contentType": getattr(file, "content_type", ""),
            },
            "visualSignals": visual,
        }

    items = ebay_result.get("items", [])
    top_match = choose_top_match(items, query=query, ocr_text=ocr_text)

    return {
        "success": True,
        "topMatch": top_match,
        "matches": items,
        "message": "Match con OCR + búsqueda automática en eBay completado.",
        "queryUsed": query,
        "ocrText": ocr_text[:700],
        "cleanTokens": clean_tokens_from_ocr(ocr_text),
        "yearsDetected": extract_years(ocr_text),
        "imageInfo": {
            "width": width,
            "height": height,
            "filename": getattr(file, "filename", ""),
            "contentType": getattr(file, "content_type", ""),
        },
        "visualSignals": visual,
    }
