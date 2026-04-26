import os


class Settings:
    APP_NAME = "Hot Wheels Visual Backend"
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    BASE_URL = os.getenv(
        "BASE_URL",
        "https://hotwheels-visual-backend.onrender.com"
    )

    EBAY_ENV = os.getenv("EBAY_ENV", "sandbox")
    EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "")
    EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "")

    WIKI_BASE = "https://hotwheels.fandom.com"
    WIKI_SEARCH_URL = f"{WIKI_BASE}/wiki/Special:Search?query="

    USER_AGENT = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }


settings = Settings()
