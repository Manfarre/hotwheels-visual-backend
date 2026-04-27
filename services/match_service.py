import re
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

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


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


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


def extract_years(text: str) -> List[str]:
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
    return unique_keep_order(years)


def crop_by_percent(img: Image.Image, box: Tuple[float, float, float, float]) -> Image.Image:
    w, h = img.size
    left = int(w * box[0])
    top = int(h * box[1])
    right = int(w * box[2])
    bottom = int(h * box[3])

    left = max(0, min(left, w - 1))
    top = max(0, min(top, h - 1))
    right = max(left + 1, min(right, w))
    bottom = max(top + 1, min(bottom, h))

    return img.crop((left, top, right, bottom))


def preprocess_for_ocr(img: Image.Image) -> List[Image.Image]:
    variants = []

    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.SHARPEN)

    big = gray.resize((gray.width * 2, gray.height * 2))
    variants.append(big)

    high_contrast = ImageEnhance.Contrast(big).enhance(2.0)
    variants.append(high_contrast)

    sharp = high_contrast.filter(ImageFilter.SHARPEN)
    variants.append(sharp)

    bw = sharp.point(lambda p: 255 if p > 150 else 0)
    variants.append(bw)

    return variants


def run_tesseract(img: Image.Image, psm: int) -> str:
    try:
        import pytesseract
        config = f"--oem 3 --psm {psm}"
        return pytesseract.image_to_string(img, config=config) or ""
    except Exception:
        return ""


def extract_ocr_text_by_regions(img: Image.Image) -> str:
    regions = [
        ("full", (0.00, 0.00, 1.00, 1.00)),
        ("upper_main", (0.05, 0.05, 0.95, 0.55)),
        ("name_band_top", (0.05, 0.18, 0.95, 0.34)),
        ("name_band_mid", (0.05, 0.28, 0.95, 0.42)),
        ("name_band_low", (0.05, 0.35, 0.95, 0.50)),
        ("center_title", (0.15, 0.18, 0.88, 0.42)),
        ("right_vertical", (0.82, 0.08, 0.98, 0.58)),
        ("top_right", (0.70, 0.05, 0.98, 0.28)),
        ("middle_strip", (0.08, 0.25, 0.92, 0.45)),
    ]

    texts: List[str] = []

    for _, box in regions:
        region = crop_by_percent(img, box)
        variants = preprocess_for_ocr(region)

        for variant in variants:
            for psm in [6, 7, 11]:
                text = run_tesseract(variant, psm=psm)
                if text and text.strip():
                    texts.append(text.strip())

    return "\n".join(unique_keep_order(texts))


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
        "EXCLUSIVE", "LIMITED", "EDITION", "MAINLINE", "PREMIUM",
        "SCANNER", "ATRAS", "ATRÁS", "PRECIO", "FUENTE", "QUERY",
        "USED", "OCR", "BACKEND", "CONFIABLE", "COINCIDENCIA"
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
        "DERECHOS", "RESULTADOS", "IMAGENES", "INFORMACION",
        "SCANNER", "RESULTADO", "ATRAS", "ATRÁS", "PRECIO", "FUENTE",
        "OCR LOCAL", "SIN COINCIDENCIA", "QUERY USADA"
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
    text = normalize_text(ocr_text)

    known_keywords = [
        "CLASSIC TV SERIES BATMOBILE",
        "BATMOBILE",
        "BEACH BOMB TOO",
        "BEACH BOMB",
        "CANDY STRIPER",
        "BONE SHAKER",
        "DRAG BUS",
        "CUSTOM VOLKSWAGEN BEETLE",
        "VOLKSWAGEN BEETLE",
        "BEETLE",
        "CAMARO",
        "MUSTANG",
        "CHEVY",
        "FORD",
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
    ]

    for keyword in known_keywords:
        if keyword in text:
            return keyword

    candidate_phrases: List[str] = []

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
        "BATMOBILE", "BEACH", "BOMB", "CANDY", "STRIPER", "CAMARO",
        "MUSTANG", "CHEVY", "FORD", "BEETLE", "VOLKSWAGEN",
        "CORVETTE", "PORSCHE", "CHARGER", "CHALLENGER", "COBRA",
        "BUS", "SHAKER"
    }

    for phrase in candidate_phrases:
        if any(term in phrase for term in preferred_terms):
            return phrase

    if len(tokens) >= 2:
        return " ".join(tokens[:3])

    return tokens[0] if tokens else ""


def build_queries_from_ocr(ocr_text: str) -> List[str]:
    text = normalize_text(ocr_text)
    if not text:
        return ["hot wheels"]

    years = extract_years(text)
    useful_tokens = clean_tokens_from_ocr(text)
    phrase = infer_model_phrase(text)

    queries: List[str] = []

    if phrase:
        queries.append(phrase)
        queries.append(f"hot wheels {phrase}")

    if useful_tokens:
        queries.append(" ".join(useful_tokens[:4]))
        queries.append(f"hot wheels {' '.join(useful_tokens[:3])}")

    if years and phrase:
        queries.append(f"{phrase} {years[0]}")
        queries.append(f"hot wheels {phrase} {years[0]}")

    queries.append("hot wheels")

    return unique_keep_order([q for q in queries if q.strip()])


def strong_ocr_tokens(ocr_text: str) -> List[str]:
    tokens = clean_tokens_from_ocr(ocr_text)
    preferred = {
        "BATMOBILE", "BEACH", "BOMB", "TOO", "CANDY", "STRIPER",
        "CAMARO", "MUSTANG", "CHEVY", "FORD", "BEETLE", "VOLKSWAGEN",
        "CORVETTE", "PORSCHE", "CHARGER", "CHALLENGER", "COBRA",
        "BUS", "SHAKER", "CLASSIC", "TV"
    }

    strong = [t for t in tokens if t in preferred]
    return unique_keep_order(strong) if strong else tokens[:5]


def score_item_against_query(item: Dict[str, Any], query: str, ocr_text: str) -> float:
    title = item.get("title", "")
    title_n = normalize_text(title)
    query_n = normalize_text(query)
    ocr_n = normalize_text(ocr_text)

    score = 0.0
    score += similarity(title_n, query_n) * 3.8

    if ocr_n:
        score += similarity(title_n, ocr_n) * 1.0

    strong_tokens = strong_ocr_tokens(ocr_text)
    matched_strong = 0

    for token in strong_tokens[:8]:
        if token in title_n:
            score += 1.4
            matched_strong += 1

    for year in extract_years(ocr_text):
        if year in title_n:
            score += 0.8

    phrase = infer_model_phrase(ocr_text)
    phrase_n = normalize_text(phrase)
    if phrase_n and phrase_n in title_n:
        score += 4.5

    if strong_tokens and matched_strong == 0:
        score -= 3.5
    elif strong_tokens and matched_strong == 1:
        score -= 0.8

    if "BATMOBILE" in query_n and "BATMOBILE" not in title_n:
        score -= 5.0
    if "BEACH BOMB" in query_n and "BEACH" not in title_n and "BOMB" not in title_n:
        score -= 5.0
    if "CANDY STRIPER" in query_n and ("CANDY" not in title_n or "STRIPER" not in title_n):
        score -= 5.0
    if "BEETLE" in query_n and "BEETLE" not in title_n and "VOLKSWAGEN" not in title_n:
        score -= 5.0
    if "CAMARO" in query_n and "CAMARO" not in title_n:
        score -= 5.0

    return round(score, 4)


def choose_top_match(
    items: List[Dict[str, Any]],
    query: str,
    ocr_text: str
) -> Optional[Dict[str, Any]]:
    if not items:
        return None

    scored = []
    for item in items:
        s = score_item_against_query(item, query, ocr_text)
        scored.append((item, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    best_item, best_score = scored[0]

    if best_score < 2.8:
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


def fetch_best_online_match(ocr_text: str) -> Dict[str, Any]:
    queries = build_queries_from_ocr(ocr_text)

    all_items: List[Dict[str, Any]] = []
    used_queries: List[str] = []

    for query in queries[:5]:
        result = search_ebay_items(query=query, limit=8)
        used_queries.append(query)

        if result.get("success"):
            items = result.get("items", [])
            all_items.extend(items)

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in all_items:
        key = (
            item.get("title", ""),
            item.get("itemWebUrl", "")
        )
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    top_match = None
    best_query = queries[0] if queries else "hot wheels"

    if deduped:
        candidates = []
        for query in used_queries:
            candidate = choose_top_match(deduped, query=query, ocr_text=ocr_text)
            if candidate:
                candidates.append((candidate, candidate.get("score", 0.0), query))

        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            top_match, _, best_query = candidates[0]

    return {
        "topMatch": top_match,
        "matches": deduped[:10],
        "queryUsed": best_query,
        "queriesTried": used_queries,
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
    ocr_text = extract_ocr_text_by_regions(img)

    online_result = fetch_best_online_match(ocr_text)
    top_match = online_result.get("topMatch")
    matches = online_result.get("matches", [])
    query_used = online_result.get("queryUsed")
    queries_tried = online_result.get("queriesTried", [])

    return {
        "success": True,
        "topMatch": top_match,
        "matches": matches,
        "message": (
            "Match online completado."
            if top_match is not None
            else "No se encontró una coincidencia online confiable."
        ),
        "queryUsed": query_used,
        "queriesTried": queries_tried,
        "ocrText": ocr_text[:1000],
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
