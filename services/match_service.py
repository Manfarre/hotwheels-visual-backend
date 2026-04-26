import re
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

WIKI_BASE = "https://hotwheels.fandom.com"
WIKI_SEARCH_URL = f"{WIKI_BASE}/wiki/Special:Search?query="


# --------------------------------------------------
# UTILIDADES BÁSICAS
# --------------------------------------------------
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


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def safe_get(url: str, timeout: int = 20) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r
        return None
    except Exception:
        return None


# --------------------------------------------------
# OCR LIMPIO Y SEÑALES
# --------------------------------------------------
def clean_ocr_lines(ocr_text: str) -> List[str]:
    lines_raw = re.split(r"[\n\r]+", ocr_text or "")
    blocked_patterns = [
        "TIKTOK", "FACEBOOK", "INSTAGRAM", "EBAY", "MERCADO",
        "GOOGLE", "GUARDAR", "COMPARTIR", "DERECHOS",
        "INFORMACION", "INFORMACIÓN", "RESULTADOS", "BUSCAR",
        "ARTICULO", "ARTÍCULO", "IR >", "IR>", "POSIBLE",
        "IMAGENES", "IMÁGENES", "AUTOR", "MÁS", "MAS"
    ]

    cleaned = []
    for line in lines_raw:
        line = normalize_text(line)
        if not line:
            continue

        if len(line) <= 1:
            continue

        letters = sum(1 for ch in line if ch.isalpha())
        digits = sum(1 for ch in line if ch.isdigit())

        if letters < 2 and digits < 2:
            continue

        if any(bp in line for bp in blocked_patterns):
            continue

        cleaned.append(line)

    return unique_keep_order(cleaned)


def extract_years(text: str) -> List[str]:
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
    return unique_keep_order(years)


def extract_fractions(text: str) -> List[str]:
    fractions = re.findall(r"\b\d{1,3}\s*/\s*\d{1,3}\b", text)
    normalized = [f.replace(" ", "") for f in fractions]
    return unique_keep_order(normalized)


def extract_series(text: str) -> str:
    candidates = [
        "MAINLINE",
        "PREMIUM",
        "CLASSICS",
        "CHECKMATE",
        "HW SCREEN TIME",
        "BATMAN",
        "RED LINE CLUB",
        "RLC",
        "SERIES ONE",
        "SERIES 1",
        "HOLIDAY RACERS",
        "TOONED",
        "EXPERIMOTORS",
        "HW HOT TRUCKS",
        "MUSCLE MANIA",
        "FAST FOODIE",
    ]
    t = normalize_text(text)
    for c in candidates:
        if c in t:
            return c
    return ""


def extract_terms(clean_lines: List[str]) -> List[str]:
    stopwords = {
        "HOT", "WHEELS", "MATTEL", "FOR", "AGES", "OVER", "DIE", "CAST",
        "METAL", "PLASTIC", "ONLINE", "EXCLUSIVE", "SERIES", "CLASSICS",
        "THE", "AND", "WITH", "COM", "WWW", "HTTP", "HTTPS", "TOY",
        "TOYS", "MODEL", "NEW", "CLUB", "LIMITED", "EDITION", "ITEM",
        "CARD", "CARDED", "LOOSE", "CAR", "CARS"
    }

    tokens: List[str] = []
    for line in clean_lines:
        for token in line.split():
            if len(token) < 3:
                continue
            if token in stopwords:
                continue
            if re.fullmatch(r"[0-9/]+", token):
                continue
            tokens.append(token)

    return unique_keep_order(tokens)


def infer_probable_name(joined_text: str) -> str:
    text = normalize_text(joined_text)
    if not text:
        return ""

    stopwords = {
        "HOT", "WHEELS", "MATTEL", "CLASSICS", "SERIES", "ONE", "CHECKMATE",
        "COLLECTOR", "COLLECTORS", "COM", "WWW", "ONLINE", "EXCLUSIVE",
        "FOR", "AGES", "OVER", "DIE", "CAST", "METAL", "PLASTIC",
        "NEW", "MODEL", "CAR", "TOY", "MAINLINE", "PREMIUM", "REDLINE",
        "CLUB", "LIMITED", "EDITION", "THE", "AND", "WITH"
    }

    tokens = [t for t in text.split() if len(t) >= 3 and t not in stopwords]

    if not tokens:
        return ""

    candidates = []

    for size in [4, 3, 2]:
        for i in range(len(tokens) - size + 1):
            phrase = " ".join(tokens[i:i + size])

            if sum(ch.isdigit() for ch in phrase) >= max(2, len(phrase) // 2):
                continue

            if re.fullmatch(r"[0-9/\- ]+", phrase):
                continue

            candidates.append(phrase)

    candidates = unique_keep_order(candidates)

    scored = []
    for phrase in candidates:
        score = 0
        words = phrase.split()

        if len(words) >= 2:
            score += 3
        if len(words) >= 3:
            score += 1
        if any(ch.isalpha() for ch in phrase):
            score += 1
        if not re.search(r"\b(COM|WWW|TIKTOK|FACEBOOK|EBAY|GOOGLE)\b", phrase):
            score += 2
        if re.search(
            r"\b(VOLKSWAGEN|BATMOBILE|BOMB|BUS|FORD|CHEVY|BONE|SHAKER|DRAG|BEETLE|CAMARO|MUSTANG|BAT)\b",
            phrase
        ):
            score += 2

        scored.append((phrase, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    if not scored:
        return ""

    best_phrase = scored[0][0]
    if len(best_phrase.replace(" ", "")) < 6:
        return ""

    return best_phrase


def extract_signal_pack(ocr_text: str) -> Dict[str, Any]:
    clean_lines = clean_ocr_lines(ocr_text)
    joined_text = " ".join(clean_lines)
    years = extract_years(joined_text)
    fractions = extract_fractions(joined_text)
    series = extract_series(joined_text)
    terms = extract_terms(clean_lines)
    probable_name = infer_probable_name(joined_text)

    return {
        "cleanLines": clean_lines,
        "joinedText": joined_text,
        "years": years,
        "fractions": fractions,
        "terms": terms,
        "series": series,
        "probableName": probable_name,
    }


def build_search_query(signals: Dict[str, Any]) -> str:
    parts: List[str] = []

    probable_name = signals.get("probableName", "")
    series = signals.get("series", "")
    years = signals.get("years", [])
    fractions = signals.get("fractions", [])
    terms = signals.get("terms", [])

    if probable_name:
        parts.append(probable_name)

    if series:
        parts.append(series)

    if fractions:
        parts.append(fractions[0])

    if years:
        parts.append(years[0])

    if not probable_name:
        blocked = {"HOT", "WHEELS", "ONLINE", "EXCLUSIVE", "MATTEL", "CLASSICS"}
        useful_terms = [t for t in terms if t not in blocked]
        parts.extend(useful_terms[:5])

    if not parts:
        parts = ["HOT WHEELS"]

    return " ".join(unique_keep_order(parts)).strip()


# --------------------------------------------------
# WIKI SEARCH
# --------------------------------------------------
def unique_result_list(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out = []
    for item in items:
        key = (item.get("title", ""), item.get("url", ""))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def parse_search_results(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: List[Dict[str, str]] = []

    selectors = [
        "ul.unified-search__results li.unified-search__result a.unified-search__result__title",
        ".mw-search-results li .mw-search-result-heading a",
        "a.unified-search__result__title",
        ".mw-search-result-heading a",
    ]

    for selector in selectors:
        for a in soup.select(selector):
            href = a.get("href", "").strip()
            title = a.get_text(" ", strip=True)
            if not href or not title:
                continue
            full_url = urljoin(WIKI_BASE, href)
            results.append({"title": title, "url": full_url})

    results = unique_result_list(results)

    if results:
        return results[:10]

    title_tag = soup.select_one("h1.page-header__title, h1#firstHeading")
    canon = soup.find("link", rel="canonical")
    if title_tag and canon and canon.get("href"):
        return [{
            "title": title_tag.get_text(" ", strip=True),
            "url": canon.get("href").strip()
        }]

    return []


def search_wiki(query: str) -> List[Dict[str, str]]:
    if not query.strip():
        return []

    url = WIKI_SEARCH_URL + quote(query)
    r = safe_get(url)
    if not r:
        return []

    return parse_search_results(r.text)


def page_visible_text(soup: BeautifulSoup) -> str:
    blocks = []
    for selector in [
        ".portable-infobox",
        ".mw-parser-output",
        "article",
        "main",
        "body",
    ]:
        node = soup.select_one(selector)
        if node:
            blocks.append(node.get_text(" ", strip=True))

    return normalize_text(" ".join(blocks))


def parse_infobox_value(soup: BeautifulSoup, labels: List[str]) -> str:
    wanted = [normalize_text(x) for x in labels]

    for row in soup.select(".portable-infobox .pi-item, .infobox tr"):
        row_text = normalize_text(row.get_text(" ", strip=True))
        for label in wanted:
            if label in row_text:
                text = row.get_text(" ", strip=True)
                text = re.sub(r"\s+", " ", text).strip()
                return text

    return ""


def infer_type_from_page_text(text: str) -> str:
    t = normalize_text(text)
    if "RLC" in t or "RED LINE CLUB" in t:
        return "RLC"
    if "PREMIUM" in t:
        return "Premium"
    if "MAINLINE" in t:
        return "Mainline"
    if "CLASSICS" in t:
        return "Classics"
    return "Por validar"


def infer_rarity_from_page_text(text: str) -> str:
    t = normalize_text(text)
    if "SUPER TREASURE HUNT" in t:
        return "Muy alta"
    if "TREASURE HUNT" in t:
        return "Alta"
    if "RLC" in t or "RED LINE CLUB" in t:
        return "Alta"
    if "PREMIUM" in t:
        return "Media-alta"
    return "Por validar"


def infer_price_placeholder(page_text: str) -> str:
    if "RLC" in page_text or "RED LINE CLUB" in page_text:
        return "Consultar mercado"
    if "PREMIUM" in page_text:
        return "Consultar mercado"
    return "Sin información"


def score_wiki_candidate(
    title: str,
    page_text: str,
    query: str,
    joined_text: str,
    probable_name: str,
    terms: List[str]
) -> float:
    title_n = normalize_text(title)
    page_n = normalize_text(page_text)
    query_n = normalize_text(query)
    joined_n = normalize_text(joined_text)

    score = 0.0
    score += similarity(title_n, query_n) * 2.5
    score += similarity(title_n, joined_n) * 1.6

    if probable_name:
        score += similarity(title_n, probable_name) * 2.8
        if probable_name in title_n:
            score += 1.4

    for term in terms[:8]:
        if term in title_n:
            score += 0.55
        elif term in page_n:
            score += 0.20

    if title_n in joined_n:
        score += 1.0

    return round(score, 4)


def fetch_wiki_candidate_details(result_item: Dict[str, str]) -> Optional[Dict[str, Any]]:
    r = safe_get(result_item["url"])
    if not r:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    visible_text = page_visible_text(soup)

    name = result_item["title"].strip()
    type_value = infer_type_from_page_text(visible_text)
    rarity_value = infer_rarity_from_page_text(visible_text)
    price_range = infer_price_placeholder(visible_text)

    year_info = parse_infobox_value(soup, ["YEAR", "RELEASE YEAR", "FIRST RELEASE"])
    country_info = parse_infobox_value(soup, ["COUNTRY"])
    wheel_info = parse_infobox_value(soup, ["WHEEL TYPE", "WHEELS"])

    extra_bits = []
    if year_info:
        extra_bits.append(f"Año: {year_info}")
    if country_info:
        extra_bits.append(f"País: {country_info}")
    if wheel_info:
        extra_bits.append(f"Rueda: {wheel_info}")

    return {
        "name": name,
        "type": type_value,
        "rarity": rarity_value,
        "priceRange": price_range,
        "pageText": visible_text,
        "extra": " | ".join(extra_bits),
        "url": result_item["url"],
    }


def build_no_match_message(signals: Dict[str, Any], reason: str) -> str:
    parts = [reason]

    if signals.get("series"):
        parts.append(f"Serie detectada: {signals['series']}")

    if signals.get("terms"):
        parts.append(f"Términos útiles: {', '.join(signals['terms'][:8])}")

    if signals.get("probableName"):
        parts.append(f"Nombre probable OCR: {signals['probableName']}")

    clean_lines = signals.get("cleanLines", [])
    if clean_lines:
        parts.append("OCR detectado:\n" + "\n".join(clean_lines[:12]))

    return "\n\n".join(parts)


def find_best_wiki_match(ocr_text: str) -> Dict[str, Any]:
    signals = extract_signal_pack(ocr_text)
    query = build_search_query(signals)
    search_results = search_wiki(query)

    if not search_results:
        return {
            "topMatch": None,
            "matches": [],
            "message": build_no_match_message(signals, "Sin resultados en wiki.")
        }

    candidates = []
    probable_name = signals.get("probableName", "")
    terms = signals.get("terms", [])
    joined_text = signals.get("joinedText", "")

    for item in search_results[:6]:
        detail = fetch_wiki_candidate_details(item)
        if not detail:
            continue

        score = score_wiki_candidate(
            title=detail["name"],
            page_text=detail["pageText"],
            query=query,
            joined_text=joined_text,
            probable_name=probable_name,
            terms=terms
        )

        detail["score"] = score
        candidates.append(detail)

    if not candidates:
        return {
            "topMatch": None,
            "matches": [],
            "message": build_no_match_message(signals, "No se pudo validar ninguna página.")
        }

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    if best["score"] < 2.2:
        return {
            "topMatch": None,
            "matches": [],
            "message": build_no_match_message(signals, "No identificado con confianza.")
        }

    similarity_value = max(0.30, min(0.98, 0.35 + (best["score"] / 6.0)))

    top_match = {
        "name": best["name"],
        "similarity": round(similarity_value, 2),
        "type": best["type"],
        "rarity": best["rarity"],
        "priceRange": best["priceRange"],
    }

    msg_parts = [
        "Match wiki general.",
        f"Query: {query}",
        f"Score: {best['score']}",
    ]

    if best.get("extra"):
        msg_parts.append(best["extra"])

    if signals.get("series"):
        msg_parts.append(f"Serie detectada: {signals['series']}")

    if signals.get("fractions"):
        msg_parts.append(f"Fracciones detectadas: {', '.join(signals['fractions'][:3])}")

    if signals.get("probableName"):
        msg_parts.append(f"Nombre probable OCR: {signals['probableName']}")

    if signals.get("cleanLines"):
        msg_parts.append("OCR detectado:\n" + "\n".join(signals["cleanLines"][:12]))

    return {
        "topMatch": top_match,
        "matches": [top_match],
        "message": "\n\n".join(msg_parts)
    }


# --------------------------------------------------
# SEÑALES VISUALES GENERALES
# --------------------------------------------------
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
    center_band = img.crop((int(width * 0.10), int(height * 0.10), int(width * 0.90), int(height * 0.70)))

    red_ratio = color_ratio(top_half, lambda r, g, b: r > 140 and r > g + 35 and r > b + 35)
    blue_ratio = color_ratio(center_band, lambda r, g, b: b > 110 and b > r + 15 and b > g + 15)
    yellow_ratio = color_ratio(top_half, lambda r, g, b: r > 150 and g > 120 and b < 130)
    dark_ratio = color_ratio(center_band, lambda r, g, b: r < 75 and g < 75 and b < 75)

    return {
        "redRatio": round(red_ratio, 3),
        "blueRatio": round(blue_ratio, 3),
        "yellowRatio": round(yellow_ratio, 3),
        "darkRatio": round(dark_ratio, 3),
    }


# --------------------------------------------------
# FUNCIÓN PRINCIPAL PARA ROUTES/MATCH.PY
# --------------------------------------------------
async def process_match(file) -> Dict[str, Any]:
    content = await file.read()

    try:
        img = Image.open(BytesIO(content)).convert("RGB")
    except Exception as e:
        return {
            "topMatch": None,
            "matches": [],
            "visualSignals": {},
            "message": f"No se pudo procesar la imagen: {str(e)}"
        }

    visual = visual_signals(img)

    ocr_text = ""

    try:
        import pytesseract
        ocr_text = pytesseract.image_to_string(img)
    except Exception:
        ocr_text = ""

    result = find_best_wiki_match(ocr_text)
    result["visualSignals"] = visual

    if not ocr_text:
        result["message"] = (
            "La imagen fue procesada correctamente, pero no se pudo extraer texto OCR. "
            "El backend ya debería iniciar sin error. Para mejores resultados, sube una imagen "
            "donde se vea claro el texto del empaque o activa OCR en el servidor.\n\n"
            + result.get("message", "")
        )

    return result
