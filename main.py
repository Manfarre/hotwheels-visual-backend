import io
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

WIKI_BASE = "https://hotwheels.fandom.com"
WIKI_SEARCH_URL = f"{WIKI_BASE}/wiki/Special:Search?query="

GENERIC_WORDS = {
    "HOT", "WHEELS", "MATTEL", "CLASSICS", "SERIES", "ONE", "CHECKMATE",
    "FOR", "AGES", "OVER", "DIE", "CAST", "METAL", "PLASTIC",
    "ONLINE", "EXCLUSIVE", "COLLECTOR", "COLLECTORS", "MAINLINE", "PREMIUM",
    "CLUB", "REDLINE", "RED", "LINE", "LIMITED", "EDITION", "MODEL",
    "CAR", "CARS", "TOY", "TOYS", "ITEM", "CARD", "CARDED", "LOOSE",
    "THE", "AND", "WITH", "NEW", "COM", "WWW", "HTTP", "HTTPS",
    "SPECIAL", "SEARCH", "WIKI", "FANDOM"
}

NOISE_WORDS = {
    "TIKTOK", "FACEBOOK", "INSTAGRAM", "EBAY", "MERCADO", "GOOGLE",
    "GUARDAR", "COMPARTIR", "DERECHOS", "INFORMACION", "INFORMACIÓN",
    "RESULTADOS", "BUSCAR", "ARTICULO", "ARTÍCULO", "POSIBLE",
    "IMAGENES", "IMÁGENES", "AUTOR", "MAS", "MÁS", "RESPONDER",
    "CHATGPT", "IR", "MENU", "MESSAGE", "MENSAJE", "LIKE", "VIEWS"
}

STRONG_MODEL_HINTS = {
    "VOLKSWAGEN", "BEETLE", "BATMOBILE", "BOMB", "BEACH", "BUS",
    "DRAG", "CHEVY", "FORD", "MERCEDES", "BONE", "SHAKER", "DODGE",
    "PONTIAC", "CAMARO", "MUSTANG", "CORVETTE", "BEL", "AIR", "NOVA",
    "PICKUP", "DELIVERY", "DOOZIE", "DEORA", "BARRACUDA", "THUNDERBIRD"
}


# --------------------------------------------------
# UTILIDADES BÁSICAS
# --------------------------------------------------
def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.upper()
    text = text.replace("\n", " ")
    for ch in [",", ".", ":", ";", "_", "(", ")", "[", "]", "{", "}", "'", '"', "|", "•", "·", "!", "?", "*", "="]:
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


def has_letters(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


def is_mainly_numeric(text: str) -> bool:
    stripped = text.replace(" ", "")
    if not stripped:
        return False
    digits = sum(1 for ch in stripped if ch.isdigit())
    return digits >= max(3, len(stripped) // 2)


# --------------------------------------------------
# OCR LIMPIO Y SEÑALES
# --------------------------------------------------
def clean_ocr_lines(ocr_text: str) -> List[str]:
    lines_raw = re.split(r"[\n\r]+", ocr_text or "")
    cleaned = []

    for line in lines_raw:
        line = normalize_text(line)
        if not line:
            continue

        if len(line) <= 1:
            continue

        if sum(1 for ch in line if ch.isalpha()) < 2 and sum(1 for ch in line if ch.isdigit()) < 2:
            continue

        if any(noise in line for noise in NOISE_WORDS):
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
        "RLC",
        "RED LINE CLUB",
        "PREMIUM",
        "CLASSICS",
        "CHECKMATE",
        "HW SCREEN TIME",
        "BATMAN",
        "SERIES ONE",
        "SERIES 1",
        "MAINLINE",
    ]
    t = normalize_text(text)
    for c in candidates:
        if c in t:
            return c
    return ""


def extract_terms(clean_lines: List[str]) -> List[str]:
    tokens: List[str] = []

    for line in clean_lines:
        for token in line.split():
            if len(token) < 3:
                continue
            if token in GENERIC_WORDS:
                continue
            if token in NOISE_WORDS:
                continue
            if re.fullmatch(r"[0-9/]+", token):
                continue
            tokens.append(token)

    return unique_keep_order(tokens)


def looks_like_good_phrase(phrase: str) -> bool:
    if not phrase:
        return False

    words = phrase.split()
    if len(words) < 2:
        return False

    useful_words = [w for w in words if w not in GENERIC_WORDS and w not in NOISE_WORDS]
    if len(useful_words) < 2:
        return False

    if is_mainly_numeric(phrase):
        return False

    if not has_letters(phrase):
        return False

    return True


def infer_probable_name(joined_text: str) -> str:
    text = normalize_text(joined_text)
    if not text:
        return ""

    tokens = [t for t in text.split() if len(t) >= 3 and t not in NOISE_WORDS]

    if not tokens:
        return ""

    candidates: List[str] = []

    for size in [4, 3, 2]:
        for i in range(len(tokens) - size + 1):
            phrase = " ".join(tokens[i:i + size]).strip()

            if not looks_like_good_phrase(phrase):
                continue

            candidates.append(phrase)

    candidates = unique_keep_order(candidates)
    if not candidates:
        return ""

    scored: List[tuple[str, float]] = []
    for phrase in candidates:
        words = phrase.split()
        useful_words = [w for w in words if w not in GENERIC_WORDS]
        score = 0.0

        score += len(useful_words) * 1.2
        score += 0.6 if len(words) >= 3 else 0.0

        strong_hits = sum(1 for w in useful_words if w in STRONG_MODEL_HINTS)
        score += strong_hits * 1.4

        generic_hits = sum(1 for w in words if w in GENERIC_WORDS)
        score -= generic_hits * 0.9

        if any(w in NOISE_WORDS for w in words):
            score -= 2.0

        letters = sum(1 for ch in phrase if ch.isalpha())
        score += min(1.2, letters / 20.0)

        scored.append((phrase, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    best_phrase, best_score = scored[0]

    if best_score < 3.2:
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


def build_search_queries(signals: Dict[str, Any]) -> List[str]:
    probable_name = signals.get("probableName", "")
    series = signals.get("series", "")
    years = signals.get("years", [])
    fractions = signals.get("fractions", [])
    terms = signals.get("terms", [])

    queries: List[str] = []

    if probable_name:
        q = [probable_name]
        if series:
            q.append(series)
        if fractions:
            q.append(fractions[0])
        queries.append(" ".join(q).strip())

    useful_terms = [t for t in terms if t not in GENERIC_WORDS and t not in NOISE_WORDS]

    if len(useful_terms) >= 2:
        q = useful_terms[:4]
        if series:
            q.append(series)
        if fractions:
            q.append(fractions[0])
        queries.append(" ".join(unique_keep_order(q)).strip())

    if series and fractions:
        queries.append(f"{series} {fractions[0]} HOT WHEELS")

    if series:
        queries.append(f"{series} HOT WHEELS")

    if years:
        queries.append(f"HOT WHEELS {years[0]}")

    queries.append("HOT WHEELS")

    return unique_keep_order([q for q in queries if q.strip()])


# --------------------------------------------------
# WIKI SEARCH
# --------------------------------------------------
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


def unique_result_list(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out = []
    for item in items:
        key = (item.get("title", ""), item.get("url", ""))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


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
    if "CLASSICS" in t:
        return "Media"
    return "Por validar"


def infer_price_placeholder(page_text: str) -> str:
    t = normalize_text(page_text)
    if "RLC" in t or "RED LINE CLUB" in t:
        return "Consultar mercado"
    if "PREMIUM" in t:
        return "Consultar mercado"
    return "Sin información"


def title_quality_score(title: str) -> float:
    title_n = normalize_text(title)
    words = [w for w in title_n.split() if w]

    useful = [w for w in words if w not in GENERIC_WORDS and w not in NOISE_WORDS]
    generic = [w for w in words if w in GENERIC_WORDS]

    score = 0.0
    score += len(useful) * 0.8
    score -= len(generic) * 0.25

    if len(useful) >= 2:
        score += 1.0

    if any(w in STRONG_MODEL_HINTS for w in useful):
        score += 1.2

    return score


def score_wiki_candidate(
    title: str,
    page_text: str,
    query: str,
    joined_text: str,
    probable_name: str,
    terms: List[str],
    fractions: List[str],
    series: str
) -> float:
    title_n = normalize_text(title)
    page_n = normalize_text(page_text)
    query_n = normalize_text(query)
    joined_n = normalize_text(joined_text)

    score = 0.0

    score += similarity(title_n, query_n) * 2.0
    score += similarity(title_n, joined_n) * 1.5
    score += title_quality_score(title_n)

    if probable_name:
        score += similarity(title_n, probable_name) * 2.2
        if probable_name in title_n:
            score += 1.6

    useful_terms = [t for t in terms if t not in GENERIC_WORDS and t not in NOISE_WORDS]
    for term in useful_terms[:8]:
        if term in title_n:
            score += 0.65
        elif term in page_n:
            score += 0.20

    for fraction in fractions[:3]:
        if fraction in page_n or fraction in title_n:
            score += 1.0

    if series and series in page_n:
        score += 0.7

    if any(h in title_n for h in STRONG_MODEL_HINTS):
        score += 0.8

    useful_title_words = [w for w in title_n.split() if w not in GENERIC_WORDS and w not in NOISE_WORDS]
    if len(useful_title_words) < 2:
        score -= 1.4

    return round(score, 4)


def is_confident_match(
    best_detail: Dict[str, Any],
    signals: Dict[str, Any]
) -> bool:
    title_n = normalize_text(best_detail.get("name", ""))
    page_n = normalize_text(best_detail.get("pageText", ""))
    probable_name = normalize_text(signals.get("probableName", ""))
    terms = signals.get("terms", [])
    fractions = signals.get("fractions", [])
    score = float(best_detail.get("score", 0.0))

    useful_title_words = [w for w in title_n.split() if w not in GENERIC_WORDS and w not in NOISE_WORDS]
    useful_term_hits = sum(1 for t in terms[:8] if t in title_n or t in page_n)
    fraction_hit = any(f in title_n or f in page_n for f in fractions[:3])
    probable_hit = bool(probable_name and (similarity(probable_name, title_n) >= 0.55 or probable_name in title_n))
    strong_hint_hit = any(h in title_n for h in STRONG_MODEL_HINTS)

    conditions_met = 0
    if score >= 3.6:
        conditions_met += 1
    if len(useful_title_words) >= 2:
        conditions_met += 1
    if useful_term_hits >= 2:
        conditions_met += 1
    if fraction_hit:
        conditions_met += 1
    if probable_hit:
        conditions_met += 1
    if strong_hint_hit:
        conditions_met += 1

    if score < 3.2:
        return False

    return conditions_met >= 3


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


def find_best_wiki_match(ocr_text: str) -> Dict[str, Any]:
    signals = extract_signal_pack(ocr_text)
    queries = build_search_queries(signals)

    all_search_results: List[Dict[str, str]] = []
    for query in queries[:4]:
        all_search_results.extend(search_wiki(query))

    all_search_results = unique_result_list(all_search_results)

    if not all_search_results:
        return {
            "acceptedMatch": False,
            "topMatch": None,
            "matches": [],
            "message": build_no_match_message(signals, "Sin resultados en wiki.")
        }

    candidates = []
    probable_name = signals.get("probableName", "")
    terms = signals.get("terms", [])
    joined_text = signals.get("joinedText", "")
    fractions = signals.get("fractions", [])
    series = signals.get("series", "")

    for item in all_search_results[:8]:
        detail = fetch_wiki_candidate_details(item)
        if not detail:
            continue

        best_query = queries[0] if queries else "HOT WHEELS"

        score = score_wiki_candidate(
            title=detail["name"],
            page_text=detail["pageText"],
            query=best_query,
            joined_text=joined_text,
            probable_name=probable_name,
            terms=terms,
            fractions=fractions,
            series=series
        )

        detail["score"] = score
        candidates.append(detail)

    if not candidates:
        return {
            "acceptedMatch": False,
            "topMatch": None,
            "matches": [],
            "message": build_no_match_message(signals, "No se pudo validar ninguna página.")
        }

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]
    accepted = is_confident_match(best, signals)

    similarity_value = max(0.30, min(0.98, 0.32 + (best["score"] / 6.0)))

    top_match = {
        "name": best["name"] if accepted else "",
        "similarity": round(similarity_value, 2),
        "type": best["type"] if accepted else "Por validar",
        "rarity": best["rarity"] if accepted else "Por validar",
        "priceRange": best["priceRange"] if accepted else "Sin información",
    }

    if accepted:
        msg_parts = [
            "Match wiki validado.",
            f"Queries usadas: {', '.join(queries[:3])}",
            f"Score: {best['score']}",
        ]

        if best.get("extra"):
            msg_parts.append(best["extra"])

        if signals.get("series"):
            msg_parts.append(f"Serie detectada: {signals['series']}")

        if signals.get("fractions"):
            msg_parts.append(f"Fracciones detectadas: {', '.join(signals['fractions'])}")

        if signals.get("cleanLines"):
            msg_parts.append("OCR detectado:\n" + "\n".join(signals["cleanLines"][:15]))

        return {
            "acceptedMatch": True,
            "topMatch": top_match,
            "matches": [top_match],
            "message": "\n\n".join(msg_parts)
        }

    return {
        "acceptedMatch": False,
        "topMatch": None,
        "matches": [],
        "message": build_no_match_message(
            signals,
            f"Sin coincidencia confiable. Mejor score encontrado: {best['score']} | Mejor título: {best['name']}"
        )
    }


def build_no_match_message(signals: Dict[str, Any], reason: str) -> str:
    parts = [reason]

    if signals.get("series"):
        parts.append(f"Serie detectada: {signals['series']}")

    if signals.get("years"):
        parts.append(f"Años detectados: {', '.join(signals['years'])}")

    if signals.get("fractions"):
        parts.append(f"Fracciones detectadas: {', '.join(signals['fractions'])}")

    useful_terms = signals.get("terms", [])
    if useful_terms:
        parts.append(f"Términos útiles: {', '.join(useful_terms[:8])}")

    if signals.get("probableName"):
        parts.append(f"Nombre probable OCR: {signals['probableName']}")

    clean_lines = signals.get("cleanLines", [])
    if clean_lines:
        parts.append("OCR detectado:\n" + "\n".join(clean_lines[:15]))

    return "\n\n".join(parts)


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
# RUTAS EXTRA PARA EBAY
# --------------------------------------------------
@app.get("/")
def root():
    return {"message": "Hot Wheels visual backend general activo"}


@app.get("/privacy")
def privacy():
    return {
        "app": "Business Technology Hot Wheels Scanner",
        "message": "Esta aplicación no almacena datos personales de usuarios de eBay. Solo utiliza información pública y señales visuales para análisis e identificación de artículos coleccionables."
    }


@app.get("/ebay/callback")
def ebay_callback(code: str = "", state: str = ""):
    return {
        "ok": True,
        "message": "Autorización recibida",
        "code": code,
        "state": state
    }


@app.get("/ebay/cancel")
def ebay_cancel():
    return {
        "ok": False,
        "message": "El usuario canceló la autorización"
    }


# --------------------------------------------------
# API PRINCIPAL
# --------------------------------------------------
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
        visual = visual_signals(img)

        if wiki_result.get("acceptedMatch") and wiki_result.get("topMatch") is not None:
            message = wiki_result.get("message", "")
            final_message = (
                f"{message}\n\n"
                f"Imagen: {width}x{height}\n"
                f"Señales visuales generales: {visual}"
            ).strip()

            return {
                "acceptedMatch": True,
                "topMatch": wiki_result["topMatch"],
                "matches": wiki_result.get("matches", []),
                "message": final_message
            }

        fallback_message = (
            f"{wiki_result.get('message', 'Sin match online.')}\n\n"
            f"Imagen: {width}x{height}\n"
            f"Señales visuales generales: {visual}"
        ).strip()

        return {
            "acceptedMatch": False,
            "topMatch": None,
            "matches": [],
            "message": fallback_message
        }

    except Exception as e:
        return {
            "acceptedMatch": False,
            "topMatch": None,
            "matches": [],
            "message": f"Error procesando imagen: {str(e)}"
        }
