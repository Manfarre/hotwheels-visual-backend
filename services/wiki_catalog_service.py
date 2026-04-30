from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from services.evidence_service import normalize_text, unique_keep_order


WIKI_API_URL = "https://hotwheels.fandom.com/api.php"
WIKI_BASE_URL = "https://hotwheels.fandom.com/wiki/"
REQUEST_TIMEOUT = 12

GENERIC_TOKENS = {
    "HOT", "WHEELS", "SERIES", "MODEL", "CAR", "CARS", "NEW",
    "COLLECTOR", "COLLECTORS", "EDITION", "LIMITED", "PREMIUM",
    "MAINLINE", "DIECAST", "METAL", "PLASTIC",
    "NOVO", "NUEVO", "NOUVEAU", "BEFORE", "CHARACTER", "CHARALTER",
    "DISNEY", "TIM", "BURTON", "NIGHTMARE", "CHRISTMAS",
    "FIRST", "EDITIONS", "2021", "2020", "2019", "2004", "1949"
}

# Tokens útiles pero demasiado ambiguos para usarse solos
WEAK_SINGLE_TOKENS = {
    "CHARGER", "FORD", "MERC", "MERCURY", "CAMARO", "MUSTANG",
    "BEETLE", "BATMOBILE", "JACK", "SANTA"
}

PACK_OR_SERIES_TERMS = {
    "SET", "SERIES", "COLLECTION", "5-PACK", "5 PACK", "3-PACK", "3 PACK",
    "4-CAR", "4 CAR", "2-PACK", "2 PACK", "BOX SET", "PLAYSET"
}

GENERIC_CONTEXT_TOKENS = {
    "CLASSIC", "CLASSICS", "BUS", "BUSES", "FORD", "CHEVY", "MUSTANG",
    "CAMARO", "BEETLE", "CAR", "CARS", "HOT"
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


def _wiki_url_from_title(title: str) -> str:
    return f"{WIKI_BASE_URL}{quote(title.replace(' ', '_'))}"


def _clean_query_parts(parts: List[str]) -> List[str]:
    cleaned: List[str] = []

    for part in parts:
        p = normalize_text(part)
        if not p:
            continue
        cleaned.append(p)

    return unique_keep_order(cleaned)


def _looks_like_bad_query(query: str) -> bool:
    q = normalize_text(query)
    if not q:
        return True

    words = [w for w in q.split() if w]

    if not words:
        return True

    if len(words) == 1:
        w = words[0]
        if w in GENERIC_TOKENS:
            return True
        if w in WEAK_SINGLE_TOKENS:
            return True
        if len(w) < 5:
            return True

    return False


def _score_query_priority(query: str, evidence: Dict[str, Any]) -> float:
    q = normalize_text(query)
    words = [w for w in q.split() if w]
    clean_tokens = [normalize_text(t) for t in evidence.get("cleanTokens", [])]
    strong_tokens = [normalize_text(t) for t in evidence.get("strongTokens", [])]
    model_lines = [normalize_text(line) for line in evidence.get("modelLines", [])]

    score = 0.0

    if len(words) >= 2:
        score += 5.0
    if len(words) >= 3:
        score += 2.0

    for line in model_lines[:8]:
        if q and q in line:
            score += 6.0

    for word in words:
        if word in strong_tokens:
            score += 2.0
        elif word in clean_tokens:
            score += 1.0

    if _looks_like_bad_query(q):
        score -= 8.0

    return round(score, 3)


def build_wiki_queries(evidence: Dict[str, Any]) -> List[str]:
    clean_tokens = [normalize_text(t) for t in evidence.get("cleanTokens", [])]
    strong_tokens = [normalize_text(t) for t in evidence.get("strongTokens", [])]
    model_lines = [normalize_text(line) for line in evidence.get("modelLines", [])]
    ocr_text = normalize_text(evidence.get("ocrText", ""))

    queries: List[str] = []

    # 1. Prioridad máxima: líneas de modelo de 2-4 palabras limpias
    for line in model_lines[:10]:
        words = [w for w in line.split() if w and w not in GENERIC_TOKENS]
        if 2 <= len(words) <= 5:
            queries.append(" ".join(words))

    # 2. Patrones visibles comunes
    token_set = set(clean_tokens + strong_tokens)

    if "SANTA" in token_set and "JACK" in token_set:
        queries.insert(0, "SANTA JACK")

    if "HARDNOZE" in token_set and "MERCURY" in token_set:
        queries.insert(0, "HARDNOZE MERCURY")
        queries.insert(1, "HARDNOZE MERC")
    elif "HARDNOZE" in token_set and "MERC" in token_set:
        queries.insert(0, "HARDNOZE MERC")

    if "VOLKSWAGEN" in token_set and "BEETLE" in token_set:
        queries.insert(0, "VOLKSWAGEN BEETLE")

    if "SHELBY" in token_set and "GT500" in token_set:
        if "67" in token_set:
            queries.insert(0, "67 SHELBY GT500")
        queries.insert(0, "SHELBY GT500")

    if "BEACH" in token_set and "BOMB" in token_set and "TOO" in token_set:
        queries.insert(0, "BEACH BOMB TOO")
    elif "BEACH" in token_set and "BOMB" in token_set:
        queries.insert(0, "BEACH BOMB")

    if "CLASSIC" in token_set and "TV" in token_set and "BATMOBILE" in token_set:
        queries.insert(0, "CLASSIC TV SERIES BATMOBILE")

    if "BATMAN" in token_set and "BEGINS" in token_set and "BATMOBILE" in token_set:
        queries.insert(0, "BATMAN BEGINS BATMOBILE")
    elif "BATMAN" in token_set and "BATMOBILE" in token_set:
        queries.insert(0, "BATMAN BATMOBILE")
    elif "BATMOBILE" in token_set:
        queries.insert(0, "BATMOBILE")

    if "CANDY" in token_set and "STRIPER" in token_set:
        queries.insert(0, "CANDY STRIPER")

    # 3. Combinaciones de strong tokens solo si son 2 o más
    filtered_strong = [
        t for t in strong_tokens
        if t not in GENERIC_TOKENS
    ]
    if len(filtered_strong) >= 3:
        queries.append(" ".join(filtered_strong[:3]))
    if len(filtered_strong) >= 2:
        queries.append(" ".join(filtered_strong[:2]))

    # 4. Combinaciones de clean tokens solo si son 2 o más
    filtered_clean = [
        t for t in clean_tokens
        if t not in GENERIC_TOKENS
    ]
    if len(filtered_clean) >= 4:
        queries.append(" ".join(filtered_clean[:4]))
    if len(filtered_clean) >= 3:
        queries.append(" ".join(filtered_clean[:3]))
    if len(filtered_clean) >= 2:
        queries.append(" ".join(filtered_clean[:2]))

    # 5. OCR fallback corto, pero solo si son 2+ palabras
    if ocr_text:
        ocr_words = [w for w in ocr_text.split() if w and w not in GENERIC_TOKENS]
        if len(ocr_words) >= 3:
            queries.append(" ".join(ocr_words[:3]))
        elif len(ocr_words) >= 2:
            queries.append(" ".join(ocr_words[:2]))

    queries = _clean_query_parts(queries)

    # Filtrar malas queries
    filtered_queries: List[str] = []
    for q in queries:
        if _looks_like_bad_query(q):
            continue
        filtered_queries.append(q)

    # Ordenar por prioridad
    filtered_queries = unique_keep_order(filtered_queries)
    filtered_queries.sort(
        key=lambda q: _score_query_priority(q, evidence),
        reverse=True
    )

    return filtered_queries[:8]


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

    if not title_n or not query_n:
        return 0.0

    from difflib import SequenceMatcher
    similarity = SequenceMatcher(None, title_n, query_n).ratio()
    score += similarity * 4.5

    query_words = [w for w in query_n.split() if w]
    title_words = [w for w in title_n.split() if w]

    matched_query_words = 0
    for word in query_words:
        if word in title_n:
            matched_query_words += 1
            score += 1.8

    # Bonus fuerte por frase completa
    if query_n == title_n:
        score += 8.0
    elif query_n in title_n:
        score += 5.0
    elif title_n in query_n:
        score += 2.5

    # Bonus por líneas OCR
    for line in model_lines[:8]:
        if query_n and query_n in line:
            score += 4.0
            break

    # Bonus por tokens fuertes
    for token in strong_tokens[:8]:
        if token and token in title_n:
            score += 1.2

    for token in clean_tokens[:8]:
        if token and token in title_n:
            score += 0.6

    # Bonus leve por snippet
    for token in strong_tokens[:4]:
        if token and token in snippet_n:
            score += 0.3

    # Penalizaciones
    if "LIST OF" in title_n:
        score -= 4.0
    if "CATEGORY" in title_n:
        score -= 3.0
    if "SERIES" in title_n and len(query_words) <= 2:
        score -= 2.0
    if any(term in title_n for term in PACK_OR_SERIES_TERMS):
        score -= 4.5

    # Si la query es de una palabra débil, bajar mucho
    if len(query_words) == 1 and query_words[0] in WEAK_SINGLE_TOKENS:
        score -= 6.0

    # Si no matchea suficiente de la query, castigar
    if len(query_words) >= 2 and matched_query_words < 2:
        score -= 4.0
    elif len(query_words) == 1 and matched_query_words == 0:
        score -= 5.0

    return round(score, 3)


def _is_candidate_strong_enough(candidate: Optional[Dict[str, Any]], query: str) -> bool:
    if not candidate:
        return False

    score = float(candidate.get("score", 0.0))
    title_n = normalize_text(candidate.get("title", ""))
    query_n = normalize_text(query)

    if not title_n or not query_n:
        return False

    query_words = [w for w in query_n.split() if w]
    matched_words = sum(1 for w in query_words if w in title_n)

    if any(term in title_n for term in PACK_OR_SERIES_TERMS):
        return False

    generic_query_words = [w for w in query_words if w in GENERIC_CONTEXT_TOKENS]
    if len(query_words) <= 3 and len(generic_query_words) == len(query_words):
        return False

    # Reglas mínimas
    if len(query_words) >= 2:
        if matched_words < 2:
            return False
        return score >= 6.5

    # Para una sola palabra, exigir más
    if len(query_words) == 1:
        if query_words[0] in WEAK_SINGLE_TOKENS:
            return False
        return score >= 8.0

    return False


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

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in sorted(all_candidates, key=lambda x: x.get("score", 0.0), reverse=True):
        key = normalize_text(item.get("title", ""))
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)

    best = deduped[0] if deduped else None

    if best is not None and not _is_candidate_strong_enough(best, best.get("matchedQuery", "")):
        best = None

    strong_candidates = []
    for item in deduped[:8]:
        if _is_candidate_strong_enough(item, item.get("matchedQuery", "")):
            strong_candidates.append(item)

    return {
        "queriesTried": queries_tried,
        "candidates": strong_candidates[:8],
        "bestCandidate": best,
    }
