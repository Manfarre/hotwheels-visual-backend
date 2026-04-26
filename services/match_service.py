from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

from app.config import settings
from app.utils.text_utils import (
    clean_ocr_lines,
    extract_fractions,
    extract_series,
    extract_terms,
    extract_years,
    infer_probable_name,
    normalize_text,
    similarity,
)


def safe_get(url: str, timeout: int = 20) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=settings.USER_AGENT, timeout=timeout)
        if r.status_code == 200:
            return r
        return None
    except Exception:
        return None


def unique_result_list(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out = []
    for item in items:
        key = (item.get("title", ""), item.get("url", ""))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def extract_signal_pack(ocr_text: str) -> Dict[str, Any]:
    clean_lines = clean_ocr_lines(ocr_text)
    joined_text = " ".join(clean_lines)

    return {
        "cleanLines": clean_lines,
        "joinedText": joined_text,
        "years": extract_years(joined_text),
        "fractions": extract_fractions(joined_text),
        "series": extract_series(joined_text),
        "terms": extract_terms(clean_lines),
        "probableName": infer_probable_name(joined_text),
    }


def build_search_queries(signals: Dict[str, Any]) -> List[str]:
    queries: List[str] = []

    probable_name = signals.get("probableName", "")
    series = signals.get("series", "")
    fractions = signals.get("fractions", [])
    years = signals.get("years", [])
    terms = signals.get("terms", [])

    if probable_name:
        q = [probable_name]
        if series:
            q.append(series)
        if fractions:
            q.append(fractions[0])
        queries.append(" ".join(q).strip())

    useful_terms = terms[:4]
    if useful_terms:
        q = useful_terms[:]
        if series:
            q.append(series)
        queries.append(" ".join(q).strip())

    if series and fractions:
        queries.append(f"{series} {fractions[0]} HOT WHEELS")

    if series:
        queries.append(f"{series} HOT WHEELS")

    if years:
        queries.append(f"HOT WHEELS {years[0]}")

    queries.append("HOT WHEELS")

    dedup = []
    seen = set()
    for q in queries:
        key = q.strip()
        if key and key not in seen:
            seen.add(key)
            dedup.append(key)

    return dedup


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
            full_url = urljoin(settings.WIKI_BASE, href)
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

    url = settings.WIKI_SEARCH_URL + quote(query)
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
                return row.get_text(" ", strip=True)

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


def fetch_wiki_candidate_details(result_item: Dict[str, str]) -> Optional[Dict[str, Any]]:
    r = safe_get(result_item["url"])
    if not r:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    visible_text = page_visible_text(soup)

    year_info = parse_infobox_value(soup, ["YEAR", "RELEASE YEAR", "FIRST RELEASE"])
    country_info = parse_infobox_value(soup, ["COUNTRY"])
    wheel_info = parse_infobox_value(soup, ["WHEEL TYPE", "WHEELS"])

    extras = []
    if year_info:
        extras.append(f"Año: {year_info}")
    if country_info:
        extras.append(f"País: {country_info}")
    if wheel_info:
        extras.append(f"Rueda: {wheel_info}")

    return {
        "name": result_item["title"].strip(),
        "type": infer_type_from_page_text(visible_text),
        "rarity": infer_rarity_from_page_text(visible_text),
        "priceRange": "Sin información",
        "pageText": visible_text,
        "extra": " | ".join(extras),
        "url": result_item["url"],
    }


def score_candidate(candidate: Dict[str, Any], signals: Dict[str, Any], query: str) -> float:
    title = normalize_text(candidate.get("name", ""))
    page_text = normalize_text(candidate.get("pageText", ""))
    probable_name = normalize_text(signals.get("probableName", ""))
    joined_text = normalize_text(signals.get("joinedText", ""))
    series = normalize_text(signals.get("series", ""))
    fractions = signals.get("fractions", [])
    terms = signals.get("terms", [])

    score = 0.0
    score += similarity(title, query) * 2.0
    score += similarity(title, joined_text) * 1.4

    if probable_name:
        score += similarity(title, probable_name) * 2.0
        if probable_name and probable_name in title:
            score += 1.2

    if series and series in page_text:
        score += 0.7

    for fraction in fractions[:3]:
        if fraction in title or fraction in page_text:
            score += 1.0

    for term in terms[:8]:
        t = normalize_text(term)
        if t in title:
            score += 0.5
        elif t in page_text:
            score += 0.2

    useful_title_words = [
        w for w in title.split()
        if w not in {"HOT", "WHEELS", "MATTEL", "CLASSICS", "SERIES"}
    ]
    if len(useful_title_words) < 2:
        score -= 1.0

    return round(score, 4)


def is_confident_match(best: Dict[str, Any], signals: Dict[str, Any]) -> bool:
    score = float(best.get("score", 0.0))
    title = normalize_text(best.get("name", ""))
    page_text = normalize_text(best.get("pageText", ""))
    probable_name = normalize_text(signals.get("probableName", ""))
    fractions = signals.get("fractions", [])
    terms = signals.get("terms", [])

    conditions = 0

    if score >= 3.2:
        conditions += 1

    useful_term_hits = sum(
        1 for t in terms[:8]
        if normalize_text(t) in title or normalize_text(t) in page_text
    )
    if useful_term_hits >= 2:
        conditions += 1

    if any(f in title or f in page_text for f in fractions[:3]):
        conditions += 1

    if probable_name and (probable_name in title or similarity(probable_name, title) >= 0.55):
        conditions += 1

    useful_title_words = [
        w for w in title.split()
        if w not in {"HOT", "WHEELS", "MATTEL", "CLASSICS", "SERIES"}
    ]
    if len(useful_title_words) >= 2:
        conditions += 1

    return score >= 3.0 and conditions >= 3


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


def build_no_match_message(signals: Dict[str, Any], reason: str) -> str:
    parts = [reason]

    if signals.get("series"):
        parts.append(f"Serie detectada: {signals['series']}")

    if signals.get("years"):
        parts.append(f"Años detectados: {', '.join(signals['years'])}")

    if signals.get("fractions"):
        parts.append(f"Fracciones detectadas: {', '.join(signals['fractions'])}")

    if signals.get("terms"):
        parts.append(f"Términos útiles: {', '.join(signals['terms'][:8])}")

    if signals.get("probableName"):
        parts.append(f"Nombre probable OCR: {signals['probableName']}")

    clean_lines = signals.get("cleanLines", [])
    if clean_lines:
        parts.append("OCR detectado:\n" + "\n".join(clean_lines[:15]))

    return "\n\n".join(parts)


def process_match(image_bytes: bytes, client_ocr: str = "") -> Dict[str, Any]:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = img.size

    signals = extract_signal_pack(client_ocr)
    queries = build_search_queries(signals)

    all_results: List[Dict[str, str]] = []
    for query in queries[:4]:
        all_results.extend(search_wiki(query))

    all_results = unique_result_list(all_results)

    if not all_results:
        return {
            "acceptedMatch": False,
            "topMatch": None,
            "matches": [],
            "message": (
                build_no_match_message(signals, "Sin resultados en wiki.")
                + f"\n\nImagen: {width}x{height}\nSeñales visuales generales: {visual_signals(img)}"
            )
        }

    candidates = []
    best_query = queries[0] if queries else "HOT WHEELS"

    for item in all_results[:8]:
        detail = fetch_wiki_candidate_details(item)
        if not detail:
            continue

        detail["score"] = score_candidate(detail, signals, best_query)
        candidates.append(detail)

    if not candidates:
        return {
            "acceptedMatch": False,
            "topMatch": None,
            "matches": [],
            "message": (
                build_no_match_message(signals, "No se pudo validar ninguna página.")
                + f"\n\nImagen: {width}x{height}\nSeñales visuales generales: {visual_signals(img)}"
            )
        }

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    if not is_confident_match(best, signals):
        return {
            "acceptedMatch": False,
            "topMatch": None,
            "matches": [],
            "message": (
                build_no_match_message(
                    signals,
                    f"Sin coincidencia confiable. Mejor score encontrado: {best['score']} | Mejor título: {best['name']}"
                )
                + f"\n\nImagen: {width}x{height}\nSeñales visuales generales: {visual_signals(img)}"
            )
        }

    similarity_value = max(0.30, min(0.98, 0.32 + (best["score"] / 6.0)))

    top_match = {
        "name": best["name"],
        "similarity": round(similarity_value, 2),
        "type": best["type"],
        "rarity": best["rarity"],
        "priceRange": best["priceRange"],
    }

    message_parts = [
        "Match wiki validado.",
        f"Queries usadas: {', '.join(queries[:3])}",
        f"Score: {best['score']}",
    ]

    if best.get("extra"):
        message_parts.append(best["extra"])

    if signals.get("series"):
        message_parts.append(f"Serie detectada: {signals['series']}")

    if signals.get("fractions"):
        message_parts.append(f"Fracciones detectadas: {', '.join(signals['fractions'])}")

    if signals.get("cleanLines"):
        message_parts.append("OCR detectado:\n" + "\n".join(signals["cleanLines"][:15]))

    message_parts.append(f"Imagen: {width}x{height}")
    message_parts.append(f"Señales visuales generales: {visual_signals(img)}")

    return {
        "acceptedMatch": True,
        "topMatch": top_match,
        "matches": [top_match],
        "message": "\n\n".join(message_parts)
    }
