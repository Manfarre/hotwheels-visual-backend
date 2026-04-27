import re
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any, Dict, List, Optional

from PIL import Image

from services.ebay_search_service import search_ebay_items


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.upper()
    text = text.replace("\n", " ")
    for ch in [",", ".", ":", ";", "_", "(", ")", "[", "]", "{", "}", "'", '"', "|", "•", "·", "™", "®"]:
        text = text.replace(ch, " ")
    text = text.replace("/", " / ")
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text)
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
        return pytesseract.image_to_string(img) or ""
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


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def clean_tokens_from_ocr(ocr_text: str) -> List[str]:
    text = normalize_text(ocr_text)

    tokens = re.findall(r"[A-Z0-9']{2,}", text)

    blocked = {
        "HOT", "WHEELS", "MATTEL", "WARNING", "AGES", "OVER", "NEW",
        "MODEL", "DIECAST", "METAL", "PLASTIC", "MADE", "THAILAND",
        "MALAYSIA", "INDONESIA", "CHINA", "COLLECTOR", "COLLECTORS",
        "SERIES", "ASSORTMENT", "ITEM", "TOY", "TOYS", "CAR", "CARS",
        "THE", "AND", "WITH", "FOR", "NOT", "USE", "ONLY", "FROM",
        "THIS", "THAT", "WWW", "HTTP", "HTTPS", "COM", "INC",
        "FACEBOOK", "TIKTOK", "GOOGLE", "RESULTADOS", "RESULTADO",
        "COMPARTIR", "GUARDAR", "DERECHOS", "IMAGENES", "IMÁGENES",
        "MAS", "MÁS", "INFORMACION", "INFORMACIÓN", "ONLINE",
        "EXCLUSIVE", "LIMITED", "EDITION", "MAINLINE", "PREMIUM"
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


def extract_clean_lines(ocr_text: str) -> List[str]:
    lines = []
    blocked_substrings = [
        "FACEBOOK", "TIKTOK", "GOOGLE", "COMPARTIR", "GUARDAR",
        "DERECHOS", "RESULTADOS", "IMAGENES", "INFORMACION"
    ]

    for raw in re.split(r"[\r\n]+", ocr_text or ""):
        line = normalize_text(raw)
        if not line:
            continue
        if len(line) < 4:
            continue
        if any(b in line for b in blocked_substrings):
            continue
        lines.append(line)

    return unique_keep_order(lines)


def infer_model_phrase(ocr_text: str) -> str:
    clean_lines = extract_clean_lines(ocr_text)
    tokens = clean_tokens_from_ocr(ocr_text)

    known_keywords = [
        "BATMOBILE",
        "BEACH BOMB",
        "BEACH BOMB TOO",
        "CAMARO",
        "MUSTANG",
        "CHEVY",
        "FORD",
        "BEETLE",
        "VOLKSWAGEN",
        "CORVETTE",
        "COBRA",
        "DODGE",
        "CHARGER",
        "CHALLENGER",
        "PORSCHE",
        "NISSAN",
        "HONDA",
        "TOYOTA",
        "TESLA",
        "BONE SHAKER",
        "DRAG BUS",
    ]

    text = normalize_text(ocr_text)

    for keyword in known_keywords:
        if keyword in text:
            if keyword == "BATMOBILE" and "CLASSIC TV SERIES" in text:
                return "CLASSIC TV SERIES BATMOBILE"
            return keyword

    candidate_phrases = []

    for line in clean_lines:
        words = [w for w in line.split() if len(w) >= 3]
        if len(words) >= 2:
            for size in [5, 4, 3, 2]:
                for i in range(len(words) - size + 1):
                    phrase = " ".join(words[i:i + size])
                    if len(phrase.replace(" ", "")) >= 8:
                        candidate_phrases.append(phrase)

    candidate_phrases = unique_keep_order(candidate_phrases)

    preferred_terms = {
        "BATMOBILE", "BEACH", "BOMB", "CAMARO", "MUSTANG", "CHEVY",
        "FORD", "BEETLE", "VOLKSWAGEN", "CORVETTE", "PORSCHE"
    }

    for phrase in candidate_phrases:
        if any(term in phrase for term in preferred_terms):
            return phrase

    if len(tokens) >= 2:
        return " ".join(tokens[:3])

    return tokens[0] if tokens else ""


def build_query_from_ocr(ocr_text: str) -> str:
    text = normalize_text(ocr_text)
    if not text:
        return "hot wheels"

    years = extract_years(text)
    useful_tokens = clean_tokens_from_ocr(text)
    phrase = infer_model_phrase(text)

    strong_model_terms = {
        "BATMOBILE", "BEACH", "BOMB", "CAMARO", "MUSTANG", "CHEVY",
        "FORD", "BEETLE", "VOLKSWAGEN", "CORVETTE", "PORSCHE",
        "CHARGER", "CHALLENGER", "COBRA", "BUS", "SHAKER"
    }

    parts: List[str] = []

    if phrase:
        parts.append(phrase)

    extra_tokens = [
        t for t in useful_tokens
        if t not in normalize_text(phrase).split()
    ]

    model_hits = [t for t in extra_tokens if t in strong_model_terms]
    if model_hits:
        parts.extend(model_hits[:2])

    if years:
        parts.append(years[0])

    if not parts:
        parts = useful_tokens[:4]

    if not parts:
        return "hot wheels"

    query = " ".join(unique_keep_order(parts)).strip()

    if len(query.split()) == 1:
        query = f"hot wheels {query}"

    return query


def strong_ocr_tokens(ocr_text: str) -> List[str]:
    tokens = clean_tokens_from_ocr(ocr_text)
    preferred = {
        "BATMOBILE", "BEACH", "BOMB", "TOO", "CAMARO", "MUSTANG",
        "CHEVY", "FORD", "BEETLE", "VOLKSWAGEN", "CORVETTE",
        "PORSCHE", "CHARGER", "CHALLENGER", "COBRA", "BUS", "SHAKER",
        "CLASSIC", "TV"
    }

    strong = [t for t in tokens if t in preferred]
    if strong:
        return unique_keep_order(strong)

    return tokens[:5]


def score_item_against_query(item: Dict[str, Any], query: str, ocr_text: str) -> float:
    title = item.get("title", "")
    title_n = normalize_text(title)
    query_n = normalize_text(query)
    ocr_n = normalize_text(ocr_text)

    score = 0.0
    score += similarity(title_n, query_n) * 3.0

    if ocr_n:
        score += similarity(title_n, ocr_n) * 1.2

    strong_tokens = strong_ocr_tokens(ocr_text)

    matched_strong = 0
    for token in strong_tokens[:8]:
        if token in title_n:
            score += 1.0
            matched_strong += 1

    years = extract_years(ocr_text)
    for year in years:
        if year in title_n:
            score += 0.8

    phrase = infer_model_phrase(ocr_text)
    phrase_n = normalize_text(phrase)
    if phrase_n and phrase_n in title_n:
        score += 3.5

    if strong_tokens and matched_strong == 0:
        score -= 2.5
    elif strong_tokens and matched_strong == 1:
        score -= 0.5

    if "BATMOBILE" in query_n and "BATMOBILE" not in title_n:
        score -= 4.0
    if "BEACH BOMB" in query_n and "BEACH" not in title_n and "BOMB" not in title_n:
        score -= 4.0
    if "CAMARO" in query_n and "CAMARO" not in title_n:
        score -= 4.0

    return round(score, 4)


def choose_top_match(items: List[Dict[str, Any]], query: str, ocr_text: str) -> Optional[Dict[str, Any]]:
    if not items:
        return None

    scored = []
    for item in items:
        s = score_item_against_query(item, query, ocr_text)
        scored.append((item, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    best_item, best_score = scored[0]

    if best_score < 1.5:
        return None

    similarity_value = max(0.30, min(0.98, 0.35 + (best_score / 6.0)))

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
