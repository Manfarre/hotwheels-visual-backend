from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from services.ebay_search_service import search_ebay_items
from services.evidence_service import normalize_text, unique_keep_order


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def build_market_queries(model_name: str) -> List[str]:
    phrase = normalize_text(model_name)
    if not phrase:
        return []

    queries: List[str] = [
        phrase,
        f"hot wheels {phrase}",
    ]

    if phrase == "67 SHELBY GT500":
        queries.extend([
            "SHELBY GT500",
            "hot wheels SHELBY GT500",
            "FORD SHELBY GT500",
        ])

    elif phrase == "SHELBY GT500":
        queries.extend([
            "hot wheels SHELBY GT500",
            "FORD SHELBY GT500",
        ])

    elif phrase == "BEACH BOMB TOO":
        queries.extend([
            "BEACH BOMB",
            "hot wheels BEACH BOMB",
            "VOLKSWAGEN BEACH BOMB",
            "VW BEACH BOMB",
        ])

    elif phrase == "BEACH BOMB":
        queries.extend([
            "hot wheels BEACH BOMB",
            "VOLKSWAGEN BEACH BOMB",
        ])

    elif phrase == "VOLKSWAGEN BEETLE":
        queries.extend([
            "VW BEETLE",
            "hot wheels VOLKSWAGEN BEETLE",
            "hot wheels VW BEETLE",
        ])

    elif phrase == "BATMAN BEGINS BATMOBILE":
        queries.extend([
            "BATMOBILE",
            "hot wheels BATMOBILE",
            "BATMAN BATMOBILE",
        ])

    elif phrase == "CLASSIC TV SERIES BATMOBILE":
        queries.extend([
            "BATMOBILE",
            "CLASSIC TV SERIES BATMOBILE",
            "hot wheels CLASSIC TV SERIES BATMOBILE",
            "BATMAN CLASSIC TV SERIES BATMOBILE",
        ])

    elif phrase == "BATMOBILE":
        queries.extend([
            "hot wheels BATMOBILE",
            "BATMAN BATMOBILE",
        ])

    elif phrase == "CANDY STRIPER":
        queries.extend([
            "hot wheels CANDY STRIPER",
        ])

    return unique_keep_order([q for q in queries if q.strip()])


def score_item_against_model(item: Dict[str, Any], model_name: str) -> float:
    title = item.get("title", "")
    title_n = normalize_text(title)
    model_n = normalize_text(model_name)

    score = 0.0
    score += similarity(title_n, model_n) * 4.5

    model_words = [w for w in model_n.split() if w]
    matched_words = 0

    for word in model_words:
        if word in title_n:
            score += 1.4
            matched_words += 1

    if model_n and model_n in title_n:
        score += 5.0

    if model_n == "67 SHELBY GT500":
        if "SHELBY" not in title_n:
            score -= 5.5
        if "GT500" not in title_n:
            score -= 5.5

    elif model_n == "SHELBY GT500":
        if "SHELBY" not in title_n:
            score -= 5.5
        if "GT500" not in title_n:
            score -= 5.5

    elif model_n == "BEACH BOMB TOO":
        if "BEACH" not in title_n or "BOMB" not in title_n:
            score -= 5.5

    elif model_n == "BEACH BOMB":
        if "BEACH" not in title_n or "BOMB" not in title_n:
            score -= 5.5

    elif model_n == "VOLKSWAGEN BEETLE":
        if "VOLKSWAGEN" not in title_n and "VW" not in title_n:
            score -= 4.0
        if "BEETLE" not in title_n:
            score -= 5.0

    elif model_n == "BATMAN BEGINS BATMOBILE":
        if "BATMOBILE" not in title_n:
            score -= 5.5
        if "BATMAN" not in title_n:
            score -= 2.0

    elif model_n == "BATMOBILE":
        if "BATMOBILE" not in title_n:
            score -= 5.5

    elif model_n == "CANDY STRIPER":
        if "CANDY" not in title_n or "STRIPER" not in title_n:
            score -= 5.5

    if matched_words == 0:
        score -= 3.0

    return round(score, 4)


def choose_top_market_match(
    items: List[Dict[str, Any]],
    model_name: str
) -> Optional[Dict[str, Any]]:
    if not items:
        return None

    scored: List[tuple[Dict[str, Any], float]] = []
    for item in items:
        s = score_item_against_model(item, model_name)
        scored.append((item, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    best_item, best_score = scored[0]

    if best_score < 3.0:
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
        "sourceQuery": best_item.get("sourceQuery", ""),
    }


def run_market_search_round(queries: List[str], limit: int = 6) -> Dict[str, Any]:
    all_items: List[Dict[str, Any]] = []
    used_queries: List[str] = []

    for query in queries:
        used_queries.append(query)
        result = search_ebay_items(query=query, limit=limit)

        if result.get("success"):
            items = result.get("items", [])
            for item in items:
                enriched = dict(item)
                enriched["sourceQuery"] = query
                all_items.append(enriched)

        if len(all_items) >= 10:
            break

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in all_items:
        key = (item.get("title", ""), item.get("itemWebUrl", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    return {
        "items": deduped,
        "usedQueries": used_queries,
    }


def fetch_market_data(model_name: str) -> Dict[str, Any]:
    queries = build_market_queries(model_name)
    if not queries:
        return {
            "acceptedMatch": False,
            "topMatch": None,
            "matches": [],
            "queryUsed": "",
            "queriesTried": [],
        }

    first_round = run_market_search_round(queries[:6], limit=6)

    items = first_round.get("items", [])
    used_queries = first_round.get("usedQueries", [])

    top_match = None
    query_used = queries[0] if queries else "hot wheels"

    if items:
        candidate = choose_top_market_match(items, model_name)
        if candidate is not None:
            top_match = candidate
            query_used = candidate.get("sourceQuery", query_used)

    return {
        "acceptedMatch": top_match is not None,
        "topMatch": top_match,
        "matches": items[:10],
        "queryUsed": query_used,
        "queriesTried": unique_keep_order(used_queries),
    }
