from typing import Any, Dict, List, Optional


def build_top_match(
    name: str = "",
    similarity: float = 0.0,
    item_type: str = "Desconocido",
    rarity: str = "Desconocida",
    price_range: str = "Sin información"
) -> Dict[str, Any]:
    return {
        "name": name,
        "similarity": similarity,
        "type": item_type,
        "rarity": rarity,
        "priceRange": price_range,
    }


def build_match_response(
    top_match: Optional[Dict[str, Any]] = None,
    matches: Optional[List[Dict[str, Any]]] = None,
    message: str = ""
) -> Dict[str, Any]:
    return {
        "topMatch": top_match,
        "matches": matches or [],
        "message": message.strip()
    }
