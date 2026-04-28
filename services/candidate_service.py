from typing import Any, Dict, List

from services.evidence_service import normalize_text
from services.wiki_catalog_service import search_wiki_catalog


KNOWN_MODEL_PHRASES = [
    "CLASSIC TV SERIES BATMOBILE",
    "BATMAN BEGINS BATMOBILE",
    "BATMAN BEGINS",
    "BATMOBILE",
    "BEACH BOMB TOO",
    "BEACH BOMB",
    "CANDY STRIPER",
    "67 SHELBY GT500",
    "SHELBY GT500",
    "CUSTOM VOLKSWAGEN BEETLE",
    "VOLKSWAGEN BEETLE",
    "BONE SHAKER",
    "DRAG BUS",
    "CAMARO",
    "MUSTANG",
    "CHEVY",
    "FORD",
    "BEETLE",
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


def infer_model_phrase_from_evidence(evidence: Dict[str, Any]) -> str:
    ocr_text = normalize_text(evidence.get("ocrText", ""))
    clean_tokens = [normalize_text(t) for t in evidence.get("cleanTokens", [])]
    model_lines = [normalize_text(line) for line in evidence.get("modelLines", [])]

    combined_texts = [ocr_text] + model_lines
    if clean_tokens:
        combined_texts.append(" ".join(clean_tokens))

    for keyword in KNOWN_MODEL_PHRASES:
        if any(keyword in part for part in combined_texts):
            return keyword

    for line in model_lines:
        if "SHELBY" in line and "GT500" in line:
            if "67" in line:
                return "67 SHELBY GT500"
            return "SHELBY GT500"

        if "CANDY" in line and "STRIPER" in line:
            return "CANDY STRIPER"

        if "BEACH" in line and "BOMB" in line:
            if "TOO" in line:
                return "BEACH BOMB TOO"
            return "BEACH BOMB"

        if "BATMOBILE" in line:
            if "BATMAN BEGINS" in line:
                return "BATMAN BEGINS BATMOBILE"
            if "CLASSIC TV SERIES" in line:
                return "CLASSIC TV SERIES BATMOBILE"
            return "BATMOBILE"

        if "VOLKSWAGEN" in line and "BEETLE" in line:
            return "VOLKSWAGEN BEETLE"

    token_set = set(clean_tokens)

    if "SHELBY" in token_set and "GT500" in token_set:
        return "67 SHELBY GT500" if "67" in token_set else "SHELBY GT500"

    if "CANDY" in token_set and "STRIPER" in token_set:
        return "CANDY STRIPER"

    if "BEACH" in token_set and "BOMB" in token_set:
        return "BEACH BOMB TOO" if "TOO" in token_set else "BEACH BOMB"

    if "BATMOBILE" in token_set:
        return "BATMOBILE"

    if "BATMAN" in token_set and "BEGINS" in token_set:
        return "BATMAN BEGINS"

    if "VOLKSWAGEN" in token_set and "BEETLE" in token_set:
        return "VOLKSWAGEN BEETLE"

    return ""


def has_minimum_candidate_confidence(evidence: Dict[str, Any], phrase: str) -> bool:
    token_set = set(normalize_text(t) for t in evidence.get("cleanTokens", []))
    model_lines = [normalize_text(line) for line in evidence.get("modelLines", [])]
    phrase_n = normalize_text(phrase)

    if not phrase_n:
        return False

    if phrase_n == "67 SHELBY GT500":
        return (
            ("SHELBY" in token_set and "GT500" in token_set) or
            any("67 SHELBY GT500" in line for line in model_lines)
        )

    if phrase_n == "SHELBY GT500":
        return "SHELBY" in token_set and "GT500" in token_set

    if phrase_n == "BEACH BOMB TOO":
        return (
            ("BEACH" in token_set and "BOMB" in token_set and "TOO" in token_set) or
            any("BEACH BOMB TOO" in line for line in model_lines)
        )

    if phrase_n == "BEACH BOMB":
        return "BEACH" in token_set and "BOMB" in token_set

    if phrase_n == "CANDY STRIPER":
        return "CANDY" in token_set and "STRIPER" in token_set

    if phrase_n == "VOLKSWAGEN BEETLE":
        return (
            ("VOLKSWAGEN" in token_set and "BEETLE" in token_set) or
            any("VOLKSWAGEN BEETLE" in line for line in model_lines)
        )

    if phrase_n == "BATMAN BEGINS BATMOBILE":
        return "BATMAN" in token_set and "BATMOBILE" in token_set

    if phrase_n == "BATMOBILE":
        return "BATMOBILE" in token_set

    if phrase_n == "BATMAN BEGINS":
        return "BATMAN" in token_set and "BEGINS" in token_set

    return False


def score_local_candidate(evidence: Dict[str, Any], phrase: str) -> float:
    clean_tokens = [normalize_text(t) for t in evidence.get("cleanTokens", [])]
    strong_tokens = [normalize_text(t) for t in evidence.get("strongTokens", [])]
    model_lines = [normalize_text(line) for line in evidence.get("modelLines", [])]
    token_set = set(clean_tokens)
    phrase_n = normalize_text(phrase)

    if not phrase_n:
        return 0.0

    score = 0.0
    phrase_words = [w for w in phrase_n.split() if w]

    for word in phrase_words:
        if word in token_set:
            score += 2.0

    for word in phrase_words:
        if word in strong_tokens:
            score += 1.5

    exact_line_match = any(phrase_n in line for line in model_lines)
    if exact_line_match:
        score += 4.0

    if phrase_n == "67 SHELBY GT500":
        if any("67 SHELBY GT500" in line for line in model_lines):
            score += 6.0
        if "SHELBY" in token_set and "GT500" in token_set:
            score += 4.0
        if "67" in token_set:
            score += 2.0

    elif phrase_n == "SHELBY GT500":
        if any("67 SHELBY GT500" in line for line in model_lines):
            score -= 3.0
        if "SHELBY" in token_set and "GT500" in token_set:
            score += 4.0

    elif phrase_n == "BEACH BOMB TOO":
        if any("BEACH BOMB TOO" in line for line in model_lines):
            score += 5.0
        if "BEACH" in token_set and "BOMB" in token_set:
            score += 4.0
        if "TOO" in token_set:
            score += 1.5

    elif phrase_n == "BEACH BOMB":
        if any("BEACH BOMB TOO" in line for line in model_lines):
            score -= 2.0
        if "BEACH" in token_set and "BOMB" in token_set:
            score += 4.0

    elif phrase_n == "VOLKSWAGEN BEETLE":
        if any("VOLKSWAGEN BEETLE" in line for line in model_lines):
            score += 5.0
        if "VOLKSWAGEN" in token_set and "BEETLE" in token_set:
            score += 4.0

    elif phrase_n == "BATMAN BEGINS BATMOBILE":
        if any("BATMAN BEGINS BATMOBILE" in line for line in model_lines):
            score += 5.0
        if "BATMAN" in token_set and "BATMOBILE" in token_set:
            score += 4.0

    elif phrase_n == "BATMOBILE":
        if any("BATMAN BEGINS BATMOBILE" in line for line in model_lines):
            score -= 2.0
        if "BATMOBILE" in token_set:
            score += 4.0

    elif phrase_n == "CANDY STRIPER":
        if any("CANDY STRIPER" in line for line in model_lines):
            score += 5.0
        if "CANDY" in token_set and "STRIPER" in token_set:
            score += 4.0

    return round(score, 2)


def build_local_fallback_candidates(evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    primary_phrase = infer_model_phrase_from_evidence(evidence)
    if primary_phrase:
        candidates.append(
            {
                "name": primary_phrase,
                "score": score_local_candidate(evidence, primary_phrase),
                "reason": "local_primary_inference",
                "confidenceOk": has_minimum_candidate_confidence(evidence, primary_phrase),
                "source": "local",
            }
        )

    if primary_phrase == "67 SHELBY GT500":
        secondary = ["SHELBY GT500"]
    elif primary_phrase == "BEACH BOMB TOO":
        secondary = ["BEACH BOMB"]
    elif primary_phrase == "BATMAN BEGINS BATMOBILE":
        secondary = ["BATMOBILE", "BATMAN BEGINS"]
    elif primary_phrase == "CUSTOM VOLKSWAGEN BEETLE":
        secondary = ["VOLKSWAGEN BEETLE", "BEETLE"]
    else:
        secondary = []

    for name in secondary:
        candidates.append(
            {
                "name": name,
                "score": score_local_candidate(evidence, name),
                "reason": "local_secondary_inference",
                "confidenceOk": has_minimum_candidate_confidence(evidence, name),
                "source": "local",
            }
        )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for candidate in candidates:
        key = normalize_text(candidate["name"])
        if key and key not in seen:
            seen.add(key)
            deduped.append(candidate)

    deduped.sort(key=lambda x: x["score"], reverse=True)
    return deduped[:5]


def build_wiki_candidates(evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    wiki_result = search_wiki_catalog(evidence)
    raw_candidates = wiki_result.get("candidates", []) or []

    candidates: List[Dict[str, Any]] = []

    for item in raw_candidates:
        title = (item.get("title") or "").strip()
        if not title:
            continue

        candidates.append(
            {
                "name": title,
                "score": float(item.get("score", 0.0)),
                "reason": f"wiki_{item.get('source', 'catalog')}",
                "confidenceOk": True,
                "source": "wiki",
                "wikiTitle": item.get("title", ""),
                "wikiUrl": item.get("url", ""),
                "matchedQuery": item.get("matchedQuery", ""),
            }
        )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for candidate in candidates:
        key = normalize_text(candidate["name"])
        if key and key not in seen:
            seen.add(key)
            deduped.append(candidate)

    deduped.sort(key=lambda x: x["score"], reverse=True)
    return deduped[:5]


def build_candidates(evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    wiki_candidates = build_wiki_candidates(evidence)

    if wiki_candidates:
        return wiki_candidates

    return build_local_fallback_candidates(evidence)


def get_best_candidate(evidence: Dict[str, Any]) -> Dict[str, Any] | None:
    candidates = build_candidates(evidence)
    return candidates[0] if candidates else None
