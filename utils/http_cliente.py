from typing import Optional
import requests

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}


def safe_get(url: str, timeout: int = 20, headers: Optional[dict] = None):
    merged_headers = DEFAULT_HEADERS.copy()
    if headers:
        merged_headers.update(headers)

    try:
        response = requests.get(url, headers=merged_headers, timeout=timeout)
        if response.status_code == 200:
            return response
        return None
    except Exception:
        return None


def safe_post(url: str, data=None, json=None, timeout: int = 20, headers: Optional[dict] = None):
    merged_headers = DEFAULT_HEADERS.copy()
    if headers:
        merged_headers.update(headers)

    try:
        response = requests.post(
            url,
            data=data,
            json=json,
            headers=merged_headers,
            timeout=timeout
        )
        return response
    except Exception:
        return None
