from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from services.evidence_service import normalize_text, unique_keep_order


WIKI_API_URL = "https://hotwheels.fandom.com/api.php"
WIKI_BASE_URL = "https://hotwheels.fandom.com/wiki/"
REQUEST_TIMEOUT = 12

# Tokens demasiado genéricos para buscar solos
GENERIC_TOKENS = {
    "HOT", "WHEELS", "SERIES", "MODEL", "CAR", "CARS", "NEW",
    "COLLECTOR", "COLLECTORS", "EDITION", "LIMITED", "PREMIUM",
    "MAINLINE", "DIECAST", "METAL", "PLASTIC"
}


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "HotWheelsScanner/1.0 (+catalog-lookup)",
            "Accept": "application/json",
        }
    )
    return session


def _clean_query_parts(parts: List[str]) -> List[str]:
    cleaned: List[str] = []
    for part in parts:
        p = normalize_text(part)
        if not p:
            continue
        if p in GENERIC_TOKENS:
            continue
        cleaned.append(p)
    return unique_keep_order(cleaned)


def build_wiki_queries(evidence: Dict[str, Any]) -> List[str]:
    clean_tokens = [normalize_text(t) for t in evidence.get("cleanTokens", [])]
    strong_tokens = [normalize_text(t) for t in evidence.get("strongTokens", [])]
    model_lines = [normalize_text(line) for line in evidence.get("modelLines", [])]
    ocr_text = normalize_text(evidence.get("ocrText", ""))

    queries: List[str] = []

    # 1. líneas de modelo primero
    for line in model_lines[:5]:
        if len(line) >= 5:
            queries.append(line)

    # 2. combinaciones de tokens fuertes
    filtered_strong = [t for t in strong_tokens if t not in GENERIC_TOKENS]
    if len(filtered_strong) >= 3:
        queries.append(" ".join(filtered_strong[:3]))
    if len(filtered_strong) >= 2:
        queries.append(" ".join(filtered_strong[:2]))
    if len(filtered_strong) >= 1:
        queries.append(filtered_strong[0])

    # 3. combinaciones de clean tokens
    filtered_clean = [t for t in clean_tokens if t not in GENERIC_TOKENS]
    if len(filtered_clean) >= 4:
        queries.append(" ".join(filtered_clean[:4]))
    if len(filtered_clean) >= 3:
        queries.append(" ".join(filtered_clean[:3]))
    if len(filtered_clean) >= 2:
        queries.append(" ".join(filtered_clean[:2]))

    # 4. patrones especiales frecuentes
    token_set = set(filtered_clean + filtered_strong)

    if "SHELBY" in token_set and "GT500" in token_set:
        queries.insert(0, "67 SHELBY GT500")
        queries.insert(1, "SHELBY GT500")

    if "BEACH" in token_set and "BOMB" in token_set and "TOO" in token_set:
        queries.insert(0, "BEACH BOMB TOO")
    elif "BEACH" in token_set and "BOMB" in token_set:
        queries.insert(0, "BEACH BOMB")

    if "VOLKSWAGEN" in token_set and "BEETLE" in token_set:
        queries.insert(0, "VOLKSWAGEN BEETLE")

    if "BATMAN" in token_set and "BATMOBILE" in token_set:
        queries.insert(0, "BATMAN BEGINS BATMOBILE")
    elif "BATMOBILE" in token_set:
        queries.insert(0, "BATMOBILE")

    if "CANDY" in token_set and "STRIPER" in token_set:
        queries.insert(0, "CANDY STRIPER")

    # 5. fallback con OCR crudo corto
    if ocr_text:
        ocr_words = [w for w in ocr_text.split() if w not in GENERIC_TOKENS]
        if len(ocr_words) >= 3:
            queries.append(" ".join(ocr_words[:3]))

    queries = _clean_query_parts(queries)

    # Evitar queries demasiado cortas o ruido
    final_queries = []
    for q in queries:
        words = [w for w in q.split() if w]
        if len(words) == 1 and len(q) < 5:
            continue
        final_queries.append(q)

    return unique_keep_order(final_queries[:8])


def _wiki_url_from_title(title: str) -> str:
    return f"{WIKI_BASE_URL}{quote(title.replace(' ', '_'))}"


def search_wiki_opensearch(query: str, session: Optional[requests.Session] = None) -> List[Dict[str, Any]]:
    s = session or _session()

    params = {
        "action": "opensearch",
        "search": query,
        "limit": 8,
        "namespace": 0,
        "format": "json",
    }

    response = s.get(WIKI_API_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    results: List[Dict[str, Any]] = []

    # formato típico: [searchterm, titles[], descriptions[], urls[]]
    if isinstance(data, list) and len(data) >= 4:
        titles = data[1] or []
        descriptions = data[2] or []
        urls = data[3] or []

        for idx, title in enumerate(titles):
            desc = descriptions[idx] if idx < len(descriptions) else ""
            url = urls[idx] if idx < len(urls) else _wiki_url_from_title(title)
            results.append(
                {
                    "title": title,
                    "snippet": desc,
                    "url": url,
                    "source": "opensearch",
                }
            )

    return results


def search_wiki_fulltext(query: str, session: Optional[requests.Session] = None) -> List[Dict[str, Any]]:
    s = session or _session()

    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 8,
        "format": "json",
    }

    response = s.get(WIKI_API_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    results: List[Dict[str, Any]] = []
    for item in data.get("query", {}).get("search", []):
        title = item.get("title", "")
        results.append(
            {
                "title": title,
                "snippet": item.get("snippet", ""),
                "url": _wiki_url_from_title(title),
                "source": "search",
            }
        )

    return results


def score_wiki_candidate(candidate: Dict[str, Any], evidence: Dict[str, Any], query: str) -> float:
    title_n = normalize_text(candidate.get("title", ""))
    snippet_n = normalize_text(candidate.get("snippet", ""))
    query_n = normalize_text(query)

    clean_tokens = [normalize_text(t) for t in evidence.get("cleanTokens", [])]
    strong_tokens = [normalize_text(t) for t in evidence.get("strongTokens", [])]
    model_lines = [normalize_text(line) for line in evidence.get("modelLines", [])]

    score = 0.0

    if not title_n:
        return 0.0

    # coincidencia con query
    from difflib import SequenceMatcher
    score += SequenceMatcher(None, title_n, query_n).ratio() * 4.5

    # bonus por tokens OCR presentes en el título
    for token in strong_tokens[:6]:
        if token and token in title_n:
            score += 1.8

    for token in clean_tokens[:6]:
        if token and token in title_n:
            score += 1.0

    # bonus si el título aparece dentro de una línea modelo
    for line in model_lines[:5]:
        if title_n and title_n in line:
            score += 4.0
            break

    # bonus si la query coincide exacta/parcialmente con el título
    if query_n == title_n:
        score += 5.0
    elif query_n and query_n in title_n:
        score += 3.0

    # bonus leve por snippet
    for token in strong_tokens[:4]:
        if token and token in snippet_n:
            score += 0.5

    # penalizaciones de ambigüedad
    if "LIST OF" in title_n:
        score -= 3.0
    if "CATEGORY" in title_n:
        score -= 2.5

    return round(score, 3)


def search_wiki_catalog(evidence: Dict[str, Any]) -> Dict[str, Any]:
    queries = build_wiki_queries(evidence)
    session = _session()

    all_candidates: List[Dict[str, Any]] = []
    queries_tried: List[str] = []

    for query in queries[:6]:
        queries_tried.append(query)

        try:
            results = search_wiki_opensearch(query, session=session)
        except Exception:
            results = []

        if not results:
            try:
                results = search_wiki_fulltext(query, session=session)
            except Exception:
                results = []

        for item in results:
            scored = dict(item)
            scored["score"] = score_wiki_candidate(scored, evidence, query)
            scored["matchedQuery"] = query
            all_candidates.append(scored)

    # dedupe por título
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in sorted(all_candidates, key=lambda x: x.get("score", 0.0), reverse=True):
        key = normalize_text(item.get("title", ""))
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)

    best = deduped[0] if deduped else None

    return {
        "queriesTried": queries_tried,
        "candidates": deduped[:8],
        "bestCandidate": best,
    }
