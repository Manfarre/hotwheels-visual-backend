from typing import Any, Dict, List, Optional

from services.candidate_service import get_best_candidate
from services.evidence_service import normalize_text


def build_probable_identity(
    evidence: Dict[str, Any],
    candidate: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if not candidate:
        return None

    name = candidate.get("name", "").strip()
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
    }


def build_no_match_identity() -> Dict[str, Any]:
    return {
        "identityStatus": "no_match",
        "modelName": "",
        "confidence": 0.0,
        "condition": "Sin coincidencia confiable",
        "score": 0.0,
        "acceptedMatch": False,
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

    probable = build_probable_identity(evidence, best_candidate)
    if probable is not None:
        return probable

    return build_no_match_identity()


def build_identity_top_match(identity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    status = identity.get("identityStatus")
    model_name = (identity.get("modelName") or "").strip()

    if status != "probable" or not model_name:
        return None

    confidence = float(identity.get("confidence", 0.0))
    score = float(identity.get("score", 0.0))
    condition = identity.get("condition", "Identificación probable por OCR")

    return {
        "name": model_name,
        "price": "Sin resultado en eBay",
        "url": "",
        "image": "",
        "condition": condition,
        "similarity": round(confidence, 2),
        "score": round(score, 2),
    }
