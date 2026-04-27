import re
from io import BytesIO
from typing import Any, Dict, List

from PIL import Image

from services.ebay_search_service import search_ebay_items


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.upper()
    text = text.replace("\n", " ")
    for ch in [",", ".", ":", ";", "_", "(", ")", "[", "]", "{", "}", "'", '"', "|", "•", "·"]:
        text = text.replace(ch, " ")
    text = text.replace("/", " / ")
    text = text.replace("-", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def color_ratio(img: Image.Image, predicate) -> float:
    small = img.resize((100, 100))
    pixels = list(small.getdata())
    if not pixels:
        return 0.0
    count = sum(1 for p in pixels if predicate(p[0], p[1], p[2]))
    return count / len(pixels)


def visual_signals(img: Image.Image) -> Dict[str, float]:
    width, height = img.size

    top_half = img.crop((0, 0, width, int(height * 0.55)))
    center_band = img.crop(
        (int(width * 0.10), int(height * 0.10), int(width * 0.90), int(height * 0.70))
    )

    red_ratio = color_ratio(
        top_half,
        lambda r, g, b: r > 140 and r > g + 35 and r > b + 35
    )
    blue_ratio = color_ratio(
        center_band,
        lambda r, g, b: b > 110 and b > r + 15 and b > g + 15
    )
    yellow_ratio = color_ratio(
        top_half,
        lambda r, g, b: r > 150 and g > 120 and b < 130
    )
    dark_ratio = color_ratio(
        center_band,
        lambda r, g, b: r < 75 and g < 75 and b < 75
    )

    return {
        "redRatio": round(red_ratio, 3),
        "blueRatio": round(blue_ratio, 3),
        "yellowRatio": round(yellow_ratio, 3),
        "darkRatio": round(dark_ratio, 3),
    }


def extract_ocr_text(img: Image.Image) -> str:
    try:
        import pytesseract
        text = pytesseract.image_to_string(img)
        return text or ""
    except Exception:
        return ""


def build_query_from_ocr(ocr_text: str) -> str:
    text = normalize_text(ocr_text)

    if not text:
        return "hot wheels"

    tokens = re.findall(r"[A-Z0-9]{3,}", text)

    blocked = {
        "HOT", "WHEELS", "MATTEL", "WARNING", "AGES", "OVER", "NEW",
        "MODEL", "DIECAST", "METAL", "PLASTIC", "MADE", "IN", "THAILAND",
        "MALAYSIA", "INDONESIA", "CHINA", "COLLECTOR", "COLLECTORS",
        "SERIES", "ASSORTMENT", "ITEM", "TOY", "TOYS"
    }

    filtered: List[str] = []
    seen = set()

    for token in tokens:
        if token in blocked:
            continue
        if token.isdigit():
            continue
        if len(token) < 3:
            continue
        if token not in seen:
            seen.add(token)
            filtered.append(token)

    if filtered:
        return "hot wheels " + " ".join(filtered[:5])

    return "hot wheels"


def choose_top_match(items: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    if not items:
        return None

    first = items[0]

    return {
        "name": first.get("title", ""),
        "price": first.get("price", ""),
        "url": first.get("itemWebUrl", ""),
        "image": first.get("image", ""),
        "condition": first.get("condition", ""),
        "similarity": 0.65,
    }


async def process_match(file) -> Dict[str, Any]:
    content = await file.read()

    try:
        img = Image.open(BytesIO(content)).convert("RGB")
    except Exception as e:
        return {
            "success": False,
            "topMatch": None,
            "matches": [],
            "message": f"No se pudo procesar la imagen: {str(e)}",
            "visualSignals": {},
        }

    width, height = img.size
    visual = visual_signals(img)
    ocr_text = extract_ocr_text(img)
    query = build_query_from_ocr(ocr_text)

    ebay_result = search_ebay_items(query=query, limit=5)

    if not ebay_result.get("success"):
        return {
            "success": False,
            "topMatch": None,
            "matches": [],
            "message": ebay_result.get("message", "Falló la búsqueda en eBay"),
            "queryUsed": query,
            "ocrText": ocr_text[:500],
            "imageInfo": {
                "width": width,
                "height": height,
                "filename": getattr(file, "filename", ""),
                "contentType": getattr(file, "content_type", ""),
            },
            "visualSignals": visual,
        }

    items = ebay_result.get("items", [])
    top_match = choose_top_match(items)

    return {
        "success": True,
        "topMatch": top_match,
        "matches": items,
        "message": "Match con búsqueda automática en eBay completado.",
        "queryUsed": query,
        "ocrText": ocr_text[:500],
        "imageInfo": {
            "width": width,
            "height": height,
            "filename": getattr(file, "filename", ""),
            "contentType": getattr(file, "content_type", ""),
        },
        "visualSignals": visual,
    }
