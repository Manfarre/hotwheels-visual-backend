import base64
from typing import Any, Dict

import requests

from config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, EBAY_ENV


def get_ebay_token_url() -> str:
    if EBAY_ENV.lower() == "production":
        return "https://api.ebay.com/identity/v1/oauth2/token"
    return "https://api.sandbox.ebay.com/identity/v1/oauth2/token"


def get_ebay_scope() -> str:
    return "https://api.ebay.com/oauth/api_scope"


def get_application_token() -> Dict[str, Any]:
    if not EBAY_CLIENT_ID or not EBAY_CLIENT_SECRET:
        return {
            "success": False,
            "message": "Faltan EBAY_CLIENT_ID o EBAY_CLIENT_SECRET"
        }

    raw = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded = base64.b64encode(raw.encode()).decode()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded}",
    }

    data = {
        "grant_type": "client_credentials",
        "scope": get_ebay_scope(),
    }

    try:
        response = requests.post(
            get_ebay_token_url(),
            headers=headers,
            data=data,
            timeout=30
        )

        if response.status_code != 200:
            return {
                "success": False,
                "message": response.text
            }

        payload = response.json()

        return {
            "success": True,
            "access_token": payload.get("access_token", ""),
            "expires_in": payload.get("expires_in", 0),
            "token_type": payload.get("token_type", ""),
            "raw": payload,
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }
