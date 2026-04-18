from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
import requests
import io
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CLASSICS_URL = "https://hotwheels.fandom.com/wiki/Classics"

session = requests.Session()
session.headers.update({
    "User-Agent": "HotWheelsScanner/0.2 (Render Classics Table Parser)"
})

_cache_rows = None


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.upper()
    replacements = {
        "0": "O",
        "1": "I",
        "5": "S",
        "|": "I",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    for ch in [",", ".", ":", ";", "_", "(", ")", "[", "]", "'", '"', "!", "?"]:
        text = text.replace(ch, " ")

    text = text.replace("-", " ")
    text = text.replace("/", " / ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> list[str]:
    return [t for t in normalize_text(text).split(" ") if t.strip()]


def sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def safe_text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def abs_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://hotwheels.fandom.com" + url
    return url


def extract_first_img(cell) -> str:
    if cell is None:
        return ""
    img = cell.find("img")
    if img:
        return abs_url(img.get("data-src") or img.get("src") or "")
    a = cell.find("a")
    if a:
        return abs_url(a.get("href") or "")
    return ""


def parse_classics_table() -> list[dict]:
    global _cache_rows
    if _cache_rows is not None:
        return _cache_rows

    response = session.get(CLASSICS_URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("table")

    rows = []

    for table in tables:
        headers = [safe_text(th) for th in table.find_all("th")]
        header_text = " | ".join(headers).upper()

        if "TOY #" not in header_text or "MODEL NAME" not in header_text:
            continue

        body_rows = table.find_all("tr")
        for tr in body_rows[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 9:
                continue

            toy_number = safe_text(cells[0])
            model_name = safe_text(cells[1])
            color = safe_text(cells[2])
            year = safe_text(cells[3])
            wheel_type = safe_text(cells[4])
            country = safe_text(cells[5])
            notes = safe_text(cells[6])
            photo_loose = extract_first_img(cells[7])
            photo_carded = extract_first_img(cells[8])

            if not model_name:
                continue

            rows.append({
                "series": "Classics",
                "toyNumber": toy_number,
                "modelName": model_name,
                "color": color,
                "year": year,
                "wheelType": wheel_type,
                "country": country,
                "notes": notes,
                "photoLoose": photo_loose,
                "photoCarded": photo_carded,
            })

    _cache_rows = rows
    return rows


def field_score(ocr_normalized: str, tokens: list[str], value: str, weight: float) -> float:
    if not value:
        return 0.0

    value_norm = normalize_text(value)
    if not value_norm:
        return 0.0

    score = 0.0

    if value_norm in ocr_normalized:
        score += 1.0 * weight

    parts = [p for p in value_norm.split(" ") if len(p) >= 2]
    if parts:
        hits = 0
        fuzzy_hits = 0

        for part in parts:
            if part in ocr_normalized:
                hits += 1
                continue

            best = 0.0
            for token in tokens:
                best = max(best, sim(part, token))

            if best >= 0.88:
                fuzzy_hits += 1

        ratio = (hits + fuzzy_hits * 0.8) / len(parts)
        score += ratio * weight

    return score


def compare_row_to_ocr(row: dict, ocr_text: str) -> dict:
    ocr_normalized = normalize_text(ocr_text)
    tokens = tokenize(ocr_text)

    score = 0.0
    matched = []

    checks = [
        ("toyNumber", row["toyNumber"], 1.2),
        ("modelName", row["modelName"], 3.0),
        ("color", row["color"], 1.0),
        ("year", row["year"], 0.9),
        ("wheelType", row["wheelType"], 0.8),
        ("country", row["country"], 0.5),
        ("notes", row["notes"], 1.4),
        ("series", row["series"], 0.6),
    ]

    for label, value, weight in checks:
        s = field_score(ocr_normalized, tokens, value, weight)
        if s > 0:
            score += s
            matched.append((label, value, round(s, 2)))

    return {
        "row": row,
        "score": round(score, 3),
        "matchedFields": matched,
    }


def classify_rarity(row: dict) -> str:
    notes = normalize_text(row.get("notes", ""))
    model = normalize_text(row.get("modelName", ""))
    if "EXCLUSIVE" in notes or "CONVENTION" in notes:
        return "Alta"
    if "BEACH BOMB" in model:
        return "Alta"
    return "Media"


def build_match_payload(scored: dict) -> dict:
    row = scored["row"]
    return {
        "name": row["modelName"],
        "similarity": min(round(0.35 + scored["score"] * 0.07, 2), 0.98),
        "type": row["series"],
        "rarity": classify_rarity(row),
        "priceRange": "Pendiente eBay",
        "toyNumber": row["toyNumber"],
        "modelName": row["modelName"],
        "color": row["color"],
        "year": row["year"],
        "wheelType": row["wheelType"],
        "country": row["country"],
        "notes": row["notes"],
        "photoLoose": row["photoLoose"],
        "photoCarded": row["photoCarded"],
        "matchedFields": scored["matchedFields"],
    }


@app.get("/")
def root():
    return {"message": "Hot Wheels Classics table backend activo"}


@app.get("/classics/count")
def classics_count():
    rows = parse_classics_table()
    return {
        "series": "Classics",
        "count": len(rows),
        "source": CLASSICS_URL
    }


@app.post("/match")
async def match_hotwheel(
    image: UploadFile = File(...),
    ocr_text: str = Form("")
):
    contents = await image.read()

    try:
        img = Image.open(io.BytesIO(contents)).convert("RGB")
        width, height = img.size

        rows = parse_classics_table()
        scored = [compare_row_to_ocr(row, ocr_text) for row in rows]
        scored.sort(key=lambda x: x["score"], reverse=True)

        top_scored = [s for s in scored[:5] if s["score"] > 0]
        matches = [build_match_payload(s) for s in top_scored]

        if top_scored and top_scored[0]["score"] >= 1.4:
            top_match = build_match_payload(top_scored[0])

            return {
                "topMatch": top_match,
                "matches": matches,
                "message": (
                    f"Match por tabla Classics. "
                    f"Imagen: {width}x{height}. "
                    f"Score: {top_scored[0]['score']}. "
                    f"OCR: {normalize_text(ocr_text)}"
                )
            }

        return {
            "topMatch": None,
            "matches": matches,
            "message": (
                f"No hubo coincidencia confiable en tabla Classics. "
                f"Imagen: {width}x{height}. "
                f"OCR: {normalize_text(ocr_text)}"
            )
        }

    except Exception as e:
        return {
            "topMatch": None,
            "matches": [],
            "message": f"Error procesando imagen: {str(e)}"
        }
