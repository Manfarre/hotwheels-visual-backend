from typing import Any, Dict, List, Optional

from services.candidate_service import get_best_candidate
from services.evidence_service import normalize_text


def _build_confirmed_identity_from_wiki(candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not candidate:
        return None

    name = (candidate.get("name") or "").strip()
    if not name:
        return None

    score = float(candidate.get("score", 0.0))
    wiki_title = candidate.get("wikiTitle", name)
    wiki_url = candidate.get("wikiUrl", "")

    confidence = 0.78
    if score >= 8:
        confidence = 0.86
    if score >= 10:
        confidence = 0.91

    return {
        "identityStatus": "confirmed",
        "modelName": name,
        "confidence": round(confidence, 2),
        "condition": "Identidad validada por catálogo wiki",
        "score": round(score, 2),
        "acceptedMatch": False,
        "source": "wiki",
        "wikiTitle": wiki_title,
        "wikiUrl": wiki_url,
    }


def _build_probable_identity_from_local(
    evidence: Dict[str, Any],
    candidate: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if not candidate:
        return None

    name = (candidate.get("name") or "").strip()
    score = float(candidate.get("score", 0.0))
    confidence_ok = bool(candidate.get("confidenceOk", False))

    if not name or not confidence_ok:
        return None

    strong_tokens = evidence.get("strongTokens", []) or []
    strong_count = len(strong_tokens)

    confidence = 0.60
    if strong_count >= 2:
        confidence = 0.74
    if strong_count >= 3:
        confidence = 0.84

    if score >= 10:
        confidence = max(confidence, 0.88)
    elif score >= 7:
        confidence = max(confidence, 0.80)

    return {
        "identityStatus": "probable",
        "modelName": name,
        "confidence": round(confidence, 2),
        "condition": "Identificación probable por OCR",
        "score": round(score, 2),
        "acceptedMatch": False,
        "source": "local",
        "wikiTitle": "",
        "wikiUrl": "",
    }


def build_no_match_identity() -> Dict[str, Any]:
    return {
        "identityStatus": "no_match",
        "modelName": "",
        "confidence": 0.0,
        "condition": "Sin coincidencia confiable",
        "score": 0.0,
        "acceptedMatch": False,
        "source": "",
        "wikiTitle": "",
        "wikiUrl": "",
    }


def resolve_identity(
    evidence: Dict[str, Any],
    candidates: List[Dict[str, Any]] | None = None
) -> Dict[str, Any]:
    if not candidates:
        best_candidate = get_best_candidate(evidence)
    else:
        best_candidate = candidates[0] if candidates else None

    if not best_candidate:
        return build_no_match_identity()

    source = normalize_text(best_candidate.get("source", ""))

    if source == "WIKI":
        confirmed = _build_confirmed_identity_from_wiki(best_candidate)
        if confirmed is not None:
            return confirmed

    probable = _build_probable_identity_from_local(evidence, best_candidate)
    if probable is not None:
        return probable

    return build_no_match_identity()


def build_identity_top_match(identity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    status = identity.get("identityStatus")
    model_name = (identity.get("modelName") or "").strip()

    if status not in {"probable", "confirmed"} or not model_name:
        return None

    confidence = float(identity.get("confidence", 0.0))
    score = float(identity.get("score", 0.0))
    condition = identity.get("condition", "Identificación probable por OCR")
    wiki_url = identity.get("wikiUrl", "") or ""

    return {
        "name": model_name,
        "price": "Sin resultado en eBay",
        "url": wiki_url,
        "image": "",
        "condition": condition,
        "similarity": round(confidence, 2),
        "score": round(score, 2),
    }
