import base64
from typing import Dict, Any

import requests

from config import (
    EBAY_APP_CLIENT_ID,
    EBAY_CERT_ID,
    EBAY_RUNAME,
    EBAY_ENV,
)


def _get_token_url() -> str:
    return (
        "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
        if EBAY_ENV.lower() == "sandbox"
        else "https://api.ebay.com/identity/v1/oauth2/token"
    )


def exchange_code_for_token(code: str) -> Dict[str, Any]:
    if not EBAY_APP_CLIENT_ID or not EBAY_CERT_ID or not EBAY_RUNAME:
        return {
            "success": False,
            "message": "Faltan variables de entorno de eBay"
        }

    raw = f"{EBAY_APP_CLIENT_ID}:{EBAY_CERT_ID}"
    encoded = base64.b64encode(raw.encode()).decode()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded}",
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": EBAY_RUNAME,
    }

    try:
        response = requests.post(_get_token_url(), headers=headers, data=data, timeout=30)
        text = response.text

        if response.status_code not in (200, 201):
            return {
                "success": False,
                "message": text
            }

        json_data = response.json()

        return {
            "success": True,
            "access_token": json_data.get("access_token", ""),
            "refresh_token": json_data.get("refresh_token", ""),
            "expires_in": json_data.get("expires_in"),
            "raw": json_data
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }
