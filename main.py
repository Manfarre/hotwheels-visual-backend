from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageStat
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
    "User-Agent": "HotWheelsScanner/0.3 (Render OCR + visual wiki matcher)"
})

_cache_rows = None
_image_cache = {}


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
        "ocrScore": round(score, 3),
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


def load_remote_image(url: str):
    if not url:
        return None
    if url in _image_cache:
        return _image_cache[url]

    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        _image_cache[url] = img
        return img
    except Exception:
        return None


def average_rgb(img: Image.Image):
    small = img.resize((64, 64))
    stat = ImageStat.Stat(small)
    r, g, b = stat.mean[:3]
    return (r, g, b)


def color_distance(c1, c2):
    return ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2) ** 0.5


def color_similarity(img1: Image.Image, img2: Image.Image) -> float:
    c1 = average_rgb(img1)
    c2 = average_rgb(img2)
    dist = color_distance(c1, c2)
    max_dist = (255**2 + 255**2 + 255**2) ** 0.5
    sim_value = 1.0 - (dist / max_dist)
    return max(0.0, min(1.0, sim_value))


def crop_card_region(img: Image.Image) -> Image.Image:
    w, h = img.size
    return img.crop((0, 0, w, int(h * 0.72)))


def crop_loose_region(img: Image.Image) -> Image.Image:
    w, h = img.size
    return img.crop((int(w * 0.08), int(h * 0.42), int(w * 0.92), int(h * 0.92)))


def compare_visual(user_img: Image.Image, row: dict):
    card_ref = load_remote_image(row.get("photoCarded", ""))
    loose_ref = load_remote_image(row.get("photoLoose", ""))

    user_card = crop_card_region(user_img)
    user_loose = crop_loose_region(user_img)

    card_score = 0.0
    loose_score = 0.0

    if card_ref is not None:
        card_score = color_similarity(user_card, card_ref)

    if loose_ref is not None:
        loose_score = color_similarity(user_loose, loose_ref)

    total_visual = (card_score * 0.65) + (loose_score * 0.35)

    return {
        "cardedScore": round(card_score, 3),
        "looseScore": round(loose_score, 3),
        "visualScore": round(total_visual, 3),
    }


def build_match_payload(scored: dict) -> dict:
    row = scored["row"]
    total_score = scored["totalScore"]

    return {
        "name": row["modelName"],
        "similarity": min(round(0.30 + total_score * 0.08, 2), 0.98),
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
        "ocrScore": scored["ocrScore"],
        "cardedScore": scored["cardedScore"],
        "looseScore": scored["looseScore"],
        "visualScore": scored["visualScore"],
        "totalScore": scored["totalScore"],
    }


@app.get("/")
def root():
    return {"message": "Hot Wheels Classics visual matcher activo"}


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
        user_img = Image.open(io.BytesIO(contents)).convert("RGB")
        width, height = user_img.size

        rows = parse_classics_table()
        combined = []

        for row in rows:
            ocr_cmp = compare_row_to_ocr(row, ocr_text)
            vis_cmp = compare_visual(user_img, row)

            total_score = (ocr_cmp["ocrScore"] * 0.55) + (vis_cmp["visualScore"] * 4.0)

            combined.append({
                "row": row,
                "matchedFields": ocr_cmp["matchedFields"],
                "ocrScore": round(ocr_cmp["ocrScore"], 3),
                "cardedScore": vis_cmp["cardedScore"],
                "looseScore": vis_cmp["looseScore"],
                "visualScore": vis_cmp["visualScore"],
                "totalScore": round(total_score, 3),
            })

        combined.sort(key=lambda x: x["totalScore"], reverse=True)

        top_scored = combined[:5]
        matches = [build_match_payload(s) for s in top_scored]

        if top_scored and top_scored[0]["totalScore"] >= 1.55:
            top_match = build_match_payload(top_scored[0])

            return {
                "topMatch": top_match,
                "matches": matches,
                "message": (
                    f"Match por OCR + comparación visual wiki. "
                    f"Imagen: {width}x{height}. "
                    f"Top totalScore: {top_scored[0]['totalScore']}. "
                    f"OCR normalizado: {normalize_text(ocr_text)}"
                )
            }

        return {
            "topMatch": None,
            "matches": matches,
            "message": (
                f"No hubo coincidencia confiable. "
                f"Imagen: {width}x{height}. "
                f"OCR normalizado: {normalize_text(ocr_text)}"
            )
        }

    except Exception as e:
        return {
            "topMatch": None,
            "matches": [],
            "message": f"Error procesando imagen: {str(e)}"
        }
