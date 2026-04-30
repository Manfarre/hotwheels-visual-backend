from typing import Any, Dict

from services.candidate_service import build_candidates
from services.evidence_service import build_evidence_from_upload
from services.identity_service import build_identity_top_match, resolve_identity
from services.market_service import fetch_market_data


async def process_match(file) -> Dict[str, Any]:
    evidence = await build_evidence_from_upload(file)

    if not evidence.get("success", False):
        return {
            "success": False,
            "topMatch": None,
            "matches": [],
            "message": evidence.get("error", "No se pudo procesar la imagen."),
            "acceptedMatch": False,
            "queryUsed": "",
            "queriesTried": [],
            "ocrText": evidence.get("ocrText", ""),
            "ocrError": evidence.get("ocrError", ""),
            "cleanTokens": evidence.get("cleanTokens", []),
            "modelLines": evidence.get("modelLines", []),
            "yearsDetected": evidence.get("yearsDetected", []),
            "imageInfo": evidence.get("imageInfo", {}),
            "visualSignals": evidence.get("visualSignals", {}),
            "candidates": [],
            "identityStatus": "no_match",
        }

    quality = evidence.get("quality", {}) or {}
    likely_insufficient = bool(quality.get("likelyInsufficient", False))
    candidates = build_candidates(evidence)

    if likely_insufficient and not candidates:
        return {
            "success": False,
            "topMatch": None,
            "matches": [],
            "message": "La imagen no contiene suficiente texto confiable para identificar la tarjeta.",
            "acceptedMatch": False,
            "queryUsed": "",
            "queriesTried": [],
            "ocrText": evidence.get("ocrText", ""),
            "ocrError": evidence.get("ocrError", ""),
            "cleanTokens": evidence.get("cleanTokens", []),
            "modelLines": evidence.get("modelLines", []),
            "yearsDetected": evidence.get("yearsDetected", []),
            "imageInfo": evidence.get("imageInfo", {}),
            "visualSignals": evidence.get("visualSignals", {}),
            "candidates": [],
            "identityStatus": "no_match",
            "identitySource": "",
            "quality": quality,
        }

    identity = resolve_identity(evidence, candidates)

    identity_status = identity.get("identityStatus", "no_match")
    identity_source = identity.get("source", "")
    model_name = identity.get("modelName", "")
    identity_top_match = build_identity_top_match(identity)

    market_result: Dict[str, Any] = {
        "acceptedMatch": False,
        "topMatch": None,
        "matches": [],
        "queryUsed": "",
        "queriesTried": [],
    }

    if model_name:
        market_result = fetch_market_data(model_name)

    accepted_match = bool(market_result.get("acceptedMatch", False))
    market_top_match = market_result.get("topMatch")
    matches = market_result.get("matches", [])
    query_used = market_result.get("queryUsed", model_name if model_name else "")
    queries_tried = market_result.get("queriesTried", [])

    final_top_match = None
    message = "No se encontró una coincidencia online confiable."

    if accepted_match and market_top_match is not None:
        final_top_match = market_top_match
        message = "Match online completado."

    elif identity_status == "confirmed" and identity_top_match is not None:
        final_top_match = identity_top_match
        message = "Modelo identificado por catálogo wiki; no hubo resultado en eBay."

    elif identity_status == "probable" and identity_top_match is not None:
        final_top_match = identity_top_match
        message = "No hubo resultado en eBay; mostrando identificación probable por OCR."

    else:
        final_top_match = None
        message = "No se encontró una coincidencia online confiable."

    return {
        "success": True,
        "topMatch": final_top_match,
        "matches": matches,
        "message": message,
        "acceptedMatch": accepted_match,
        "queryUsed": query_used,
        "queriesTried": queries_tried,
        "ocrText": evidence.get("ocrText", ""),
        "ocrError": evidence.get("ocrError", ""),
        "cleanTokens": evidence.get("cleanTokens", []),
        "modelLines": evidence.get("modelLines", []),
        "yearsDetected": evidence.get("yearsDetected", []),
        "imageInfo": evidence.get("imageInfo", {}),
        "visualSignals": evidence.get("visualSignals", {}),
        "candidates": candidates,
        "identityStatus": identity_status,
        "identitySource": identity_source,
        "quality": quality,
    }
