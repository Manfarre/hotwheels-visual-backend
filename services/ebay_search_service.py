from typing import Any, Dict, List

import requests

from config import settings
from services.ebay_token_service import get_application_token


def get_browse_search_url() -> str:
    if settings.EBAY_ENV.lower() == "production":
        return "https://api.ebay.com/buy/browse/v1/item_summary/search"
    return "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search"


def normalize_ebay_item(item: Dict[str, Any]) -> Dict[str, Any]:
    price_obj = item.get("price", {}) or {}
    image_obj = item.get("image", {}) or {}

    price_value = price_obj.get("value", "")
    price_currency = price_obj.get("currency", "")

    return {
        "title": item.get("title", ""),
        "itemWebUrl": item.get("itemWebUrl", ""),
        "condition": item.get("condition", ""),
        "image": image_obj.get("imageUrl", ""),
        "price": f"{price_value} {price_currency}".strip(),
    }


def search_ebay_items(query: str, limit: int = 10) -> Dict[str, Any]:
    token_result = get_application_token()
    if not token_result.get("success"):
        return token_result

    access_token = token_result.get("access_token", "")
    if not access_token:
        return {
            "success": False,
            "message": "No se pudo obtener access token"
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    params = {
        "q": query,
        "limit": limit,
    }

    try:
        response = requests.get(
            get_browse_search_url(),
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            return {
                "success": False,
                "message": response.text
            }

        payload = response.json()
        items = payload.get("itemSummaries", []) or []

        normalized: List[Dict[str, Any]] = [
            normalize_ebay_item(item) for item in items
        ]

        return {
            "success": True,
            "count": len(normalized),
            "items": normalized,
            "raw": payload,
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }
