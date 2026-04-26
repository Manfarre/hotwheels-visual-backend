import os

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

EBAY_ENV = os.getenv("EBAY_ENV", "sandbox")
EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

WIKI_BASE = "https://hotwheels.fandom.com"
WIKI_SEARCH_URL = f"{WIKI_BASE}/wiki/Special:Search?query="
