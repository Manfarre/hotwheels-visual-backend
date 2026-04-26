from typing import Dict, Any, List

import requests

from config import EBAY_ENV


def _get_browse_url() -> str:
    return (
        "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search"
        if EBAY_ENV.lower() == "sandbox"
        else "https://api.ebay.com/buy/browse/v1/item_summary/search"
    )


def search_ebay_items(
    query: str,
    access_token: str,
    limit: int = 10
) -> Dict[str, Any]:
    if not access_token:
        return {
            "success": False,
            "message": "No hay access token"
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
            _get_browse_url(),
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            return {
                "success": False,
                "message": response.text
            }

        data = response.json()
        items = data.get("itemSummaries", [])

        simplified: List[Dict[str, Any]] = []
        for item in items:
            simplified.append({
                "title": item.get("title", ""),
                "price": (
                    f"{item.get('price', {}).get('value', '')} "
                    f"{item.get('price', {}).get('currency', '')}"
                ).strip(),
                "condition": item.get("condition", ""),
                "itemWebUrl": item.get("itemWebUrl", ""),
                "image": item.get("image", {}).get("imageUrl", "")
            })

        return {
            "success": True,
            "count": len(simplified),
            "items": simplified,
            "raw": data
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }
