import re
from io import BytesIO
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


STRONG_MODEL_TOKENS = {
    "BATMOBILE", "BATMAN", "BEACH", "BOMB", "TOO", "CANDY", "STRIPER",
    "SHELBY", "GT500", "CAMARO", "MUSTANG", "CHEVY", "FORD",
    "BEETLE", "VOLKSWAGEN", "CORVETTE", "PORSCHE", "CHARGER",
    "CHALLENGER", "COBRA", "BUS", "SHAKER", "CLASSIC", "TV", "BEGINS",
    "VAN", "HARDNOZE", "MERC", "MERCURY"
}

BLOCKED_TOKENS = {
    "HOT", "WHEELS", "MATTEL", "WARNING", "AGES", "OVER", "NEW",
    "MODEL", "DIECAST", "METAL", "PLASTIC", "MADE", "THAILAND",
    "MALAYSIA", "INDONESIA", "CHINA", "COLLECTOR", "COLLECTORS",
    "SERIES", "ASSORTMENT", "ITEM", "TOY", "TOYS", "CAR", "CARS",
    "THE", "AND", "WITH", "FOR", "NOT", "USE", "ONLY", "FROM",
    "THIS", "THAT", "WWW", "HTTP", "HTTPS", "COM", "INC",
    "FACEBOOK", "TIKTOK", "GOOGLE", "RESULTADOS", "RESULTADO",
    "COMPARTIR", "GUARDAR", "DERECHOS", "IMAGENES", "IMÁGENES",
    "MAS", "MÁS", "INFORMACION", "INFORMACIÓN", "ONLINE",
    "EXCLUSIVE", "LIMITED", "EDITION", "MAINLINE", "PREMIUM",
    "SCANNER", "ATRAS", "ATRÁS", "PRECIO", "FUENTE", "QUERY",
    "USED", "OCR", "BACKEND", "CONFIABLE", "COINCIDENCIA",
    "LIFE", "HOW", "HOR", "HOY", "VIL", "REE", "FIRST", "EDITIONS"
}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.upper()
    text = text.replace("\n", " ")
    for ch in [",", ".", ":", ";", "_", "(", ")", "[", "]", "{", "}", "'", '"', "|", "•", "·", "™", "®", "#"]:
        text = text.replace(ch, " ")
    text = text.replace("/", " / ")
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def extract_years(text: str) -> List[str]:
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
    return unique_keep_order(years)


def resize_large_image_for_processing(img: Image.Image, max_side: int = 1400) -> Image.Image:
    w, h = img.size
    max_current = max(w, h)

    if max_current <= max_side:
        return img

    scale = max_side / float(max_current)
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def upscale_small_image_for_processing(img: Image.Image, min_side: int = 900) -> Image.Image:
    w, h = img.size
    min_current = min(w, h)

    if min_current >= min_side:
        return img

    scale = min_side / float(min_current)
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def prepare_image_for_processing(img: Image.Image) -> Image.Image:
    img = upscale_small_image_for_processing(img, min_side=900)
    img = resize_large_image_for_processing(img, max_side=1600)
    return img


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


def crop_by_percent(img: Image.Image, box: Tuple[float, float, float, float]) -> Image.Image:
    w, h = img.size
    left = int(w * box[0])
    top = int(h * box[1])
    right = int(w * box[2])
    bottom = int(h * box[3])

    left = max(0, min(left, w - 1))
    top = max(0, min(top, h - 1))
    right = max(left + 1, min(right, w))
    bottom = max(top + 1, min(bottom, h))

    return img.crop((left, top, right, bottom))


def preprocess_for_ocr_fast(img: Image.Image) -> List[Image.Image]:
    variants: List[Image.Image] = []

    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.SHARPEN)

    base = gray.resize((max(1, gray.width * 2), max(1, gray.height * 2)))
    variants.append(base)

    high_contrast = ImageEnhance.Contrast(base).enhance(2.0)
    variants.append(high_contrast)

    return variants


def preprocess_for_ocr_deep(img: Image.Image) -> List[Image.Image]:
    variants: List[Image.Image] = []

    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.SHARPEN)

    base = gray.resize((max(1, gray.width * 2), max(1, gray.height * 2)))
    variants.append(base)

    high_contrast = ImageEnhance.Contrast(base).enhance(2.2)
    variants.append(high_contrast)

    sharper = high_contrast.filter(ImageFilter.SHARPEN)
    variants.append(sharper)

    bw1 = sharper.point(lambda p: 255 if p > 145 else 0)
    variants.append(bw1)

    bw2 = sharper.point(lambda p: 255 if p > 170 else 0)
    variants.append(bw2)

    return variants


def run_tesseract(img: Image.Image, psm: int) -> str:
    import pytesseract
    config = f"--oem 3 --psm {psm}"
    return pytesseract.image_to_string(img, config=config) or ""


def run_ocr_regions(
    img: Image.Image,
    regions: List[Tuple[str, Tuple[float, float, float, float], int]],
    mode: str,
) -> str:
    texts: List[str] = []

    for region_name, box, rotation in regions:
        region = crop_by_percent(img, box)

        if rotation != 0:
            region = region.rotate(rotation, expand=True)

        if mode == "fast":
            variants = preprocess_for_ocr_fast(region)
        else:
            variants = preprocess_for_ocr_deep(region)

        if mode == "fast":
            if "right_strip" in region_name:
                psms = [7, 6]
            else:
                psms = [7, 6]
        else:
            if "right_strip" in region_name:
                psms = [6, 7, 11, 12]
            elif region_name in {
                "bottom_model_name",
                "center_title",
                "name_band_top",
                "name_band_mid",
                "name_band_low",
            }:
                psms = [7, 6, 11]
            else:
                psms = [6, 7]

        for variant in variants:
            for psm in psms:
                text = run_tesseract(variant, psm=psm)
                if text and text.strip():
                    texts.append(text.strip())

    return "\n".join(unique_keep_order(texts))


def looks_like_catalog_code(token: str) -> bool:
    t = normalize_text(token)

    if re.fullmatch(r"[A-Z]{1,3}\d{3,5}", t):
        return True

    if re.fullmatch(r"\d{3,5}[A-Z]{1,3}", t):
        return True

    return False


def looks_like_garbage(token: str) -> bool:
    t = normalize_text(token)

    if len(t) < 3:
        return True

    if re.fullmatch(r"[0-9/]+", t):
        return True

    if looks_like_catalog_code(t):
        return True

    weird_sequences = [
        "AUAA", "EEE", "SNIR", "ROA", "SLS", "ETSOO", "AOR",
        "VEELS", "PELS", "PEIS", "NORE", "AMAAT", "SEMML",
        "6888", "EUNEAN", "ASASA", "SEDC", "O82", "SPYPYPH"
    ]

    if any(w in t for w in weird_sequences):
        return True

    letters_only = re.sub(r"[^A-Z]", "", t)
    if len(letters_only) >= 6:
        vowels = sum(1 for ch in letters_only if ch in "AEIOU")
        if vowels == 0:
            return True

    return False


def similarity_simple(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def canonicalize_token(token: str) -> str:
    t = normalize_text(token)

    replacements = {
        "BEARH": "BEACH",
        "SEACH": "BEACH",
        "BEACM": "BEACH",
        "BEACN": "BEACH",
        "SACH": "BEACH",
        "BEACHH": "BEACH",

        "BAM": "BOMB",
        "BAAD": "BOMB",
        "BAED": "BOMB",
        "SAMD": "BOMB",
        "SAMB": "BOMB",
        "SAND": "BOMB",
        "SAED": "BOMB",
        "BAD": "BOMB",
        "SAB": "BOMB",
        "BOMD": "BOMB",
        "BOMH": "BOMB",
        "BONB": "BOMB",

        "TEA": "TOO",
        "FEA": "TOO",
        "FOO": "TOO",
        "TED": "TOO",
        "TO0": "TOO",
        "100": "TOO",

        "BATNA": "BATMAN",
        "BATMAM": "BATMAN",
        "BATMOBLLE": "BATMOBILE",
        "BATMOB1LE": "BATMOBILE",

        "STRIPFR": "STRIPER",
        "STRIPR": "STRIPER",

        "GTSOO": "GT500",
        "GT5OO": "GT500",
        "GT5O0": "GT500",
        "GT5000": "GT500",

        "VOLKSWACE": "VOLKSWAGEN",
        "VOLKSWAGENN": "VOLKSWAGEN",

        "BEETLF": "BEETLE",

        "HARDNO2E": "HARDNOZE",
        "HARDNOSE": "HARDNOZE",
        "HARONOZE": "HARDNOZE",
        "MERC.": "MERC",
        "MERCURY.": "MERCURY",
    }

    if t in replacements:
        return replacements[t]

    for target in STRONG_MODEL_TOKENS:
        if similarity_simple(t, target) >= 0.72:
            return target

    return t


def extract_raw_tokens(ocr_text: str) -> List[str]:
    text = normalize_text(ocr_text)
    return re.findall(r"[A-Z0-9']{2,}", text)


def clean_tokens_from_ocr(ocr_text: str) -> List[str]:
    raw_tokens = extract_raw_tokens(ocr_text)

    useful: List[str] = []
    seen = set()

    for token in raw_tokens:
        token = canonicalize_token(token)

        if token in BLOCKED_TOKENS:
            continue
        if token.isdigit():
            continue
        if len(token) < 3:
            continue
        if re.fullmatch(r"[0-9/]+", token):
            continue
        if looks_like_catalog_code(token):
            continue
        if token not in STRONG_MODEL_TOKENS and looks_like_garbage(token):
            continue

        if token not in seen:
            seen.add(token)
            useful.append(token)

    return useful


def extract_clean_lines(ocr_text: str) -> List[str]:
    lines: List[str] = []
    blocked_substrings = [
        "FACEBOOK", "TIKTOK", "GOOGLE", "COMPARTIR", "GUARDAR",
        "DERECHOS", "RESULTADOS", "IMAGENES", "INFORMACION",
        "SCANNER", "RESULTADO", "ATRAS", "ATRÁS", "PRECIO", "FUENTE",
        "OCR LOCAL", "SIN COINCIDENCIA", "QUERY USADA"
    ]

    for raw in re.split(r"[\r\n]+", ocr_text or ""):
        line = normalize_text(raw)
        if not line:
            continue
        if len(line) < 4:
            continue
        if any(b in line for b in blocked_substrings):
            continue
        if looks_like_catalog_code(line):
            continue
        lines.append(line)

    return unique_keep_order(lines)


def normalized_model_lines(ocr_text: str) -> List[str]:
    normalized_lines: List[str] = []

    for line in extract_clean_lines(ocr_text):
        parts: List[str] = []
        for token in re.findall(r"[A-Z0-9']{2,}", normalize_text(line)):
            fixed = canonicalize_token(token)
            if fixed in BLOCKED_TOKENS:
                continue
            if len(fixed) < 3:
                continue
            if looks_like_catalog_code(fixed):
                continue
            parts.append(fixed)

        if parts:
            normalized_lines.append(" ".join(parts))

    return unique_keep_order(normalized_lines)


def extract_model_like_lines(ocr_text: str) -> List[str]:
    lines = normalized_model_lines(ocr_text)

    good: List[str] = []
    for line in lines:
        if any(word in line for word in STRONG_MODEL_TOKENS):
            good.append(line)
            continue

        if re.search(r"\b(19\d{2}|20\d{2})\b", line) and re.search(r"\b[A-Z]{3,}\b", line):
            good.append(line)
            continue

        if "MERC" in line or "HARDNOZE" in line:
            good.append(line)

    return unique_keep_order(good)


def strong_ocr_tokens(ocr_text: str) -> List[str]:
    tokens = clean_tokens_from_ocr(ocr_text)
    strong = [t for t in tokens if t in STRONG_MODEL_TOKENS]
    return unique_keep_order(strong) if strong else tokens[:5]


def evaluate_ocr_quality(
    original_width: int,
    original_height: int,
    ocr_text: str,
    clean_tokens: List[str],
    model_lines: List[str],
) -> Dict[str, Any]:
    warnings: List[str] = []

    if original_width < 350 or original_height < 500:
        warnings.append("input_image_small")

    useful_token_count = len(clean_tokens)
    model_line_count = len(model_lines)
    ocr_char_count = len((ocr_text or "").strip())

    likely_insufficient = False

    if useful_token_count == 0 and model_line_count == 0:
        likely_insufficient = True

    if ocr_char_count < 40 and useful_token_count <= 1:
        likely_insufficient = True

    if original_width < 320 and useful_token_count <= 2 and model_line_count == 0:
        likely_insufficient = True

    if likely_insufficient:
        warnings.append("ocr_text_insufficient")

    return {
        "likelyInsufficient": likely_insufficient,
        "warnings": warnings,
    }


def extract_ocr_text_two_phase(img: Image.Image) -> Tuple[str, str]:
    fast_regions = [
        ("center_title", (0.12, 0.16, 0.90, 0.45), 0),
        ("name_band_mid", (0.05, 0.28, 0.95, 0.44), 0),
        ("bottom_model_name", (0.15, 0.66, 0.86, 0.86), 0),
        ("right_strip_full_r90", (0.78, 0.08, 0.995, 0.96), 90),
        ("right_strip_mid_r90", (0.80, 0.28, 0.995, 0.92), 90),
    ]

    deep_regions = [
        ("full", (0.00, 0.00, 1.00, 1.00), 0),
        ("upper_main", (0.05, 0.05, 0.95, 0.58), 0),
        ("center_title", (0.12, 0.16, 0.90, 0.45), 0),
        ("name_band_top", (0.05, 0.18, 0.95, 0.34), 0),
        ("name_band_mid", (0.05, 0.28, 0.95, 0.44), 0),
        ("name_band_low", (0.05, 0.36, 0.95, 0.52), 0),
        ("bottom_model_name", (0.15, 0.66, 0.86, 0.86), 0),

        ("right_strip_full", (0.78, 0.08, 0.995, 0.96), 0),
        ("right_strip_full_r90", (0.78, 0.08, 0.995, 0.96), 90),
        ("right_strip_full_r270", (0.78, 0.08, 0.995, 0.96), 270),

        ("right_strip_mid", (0.80, 0.28, 0.995, 0.92), 0),
        ("right_strip_mid_r90", (0.80, 0.28, 0.995, 0.92), 90),
        ("right_strip_mid_r270", (0.80, 0.28, 0.995, 0.92), 270),

        ("right_strip_top", (0.80, 0.12, 0.995, 0.55), 0),
        ("right_strip_top_r90", (0.80, 0.12, 0.995, 0.55), 90),
        ("right_strip_top_r270", (0.80, 0.12, 0.995, 0.55), 270),
    ]

    fast_text = run_ocr_regions(img, fast_regions, mode="fast")
    fast_clean_tokens = clean_tokens_from_ocr(fast_text)
    fast_model_lines = extract_model_like_lines(fast_text)

    fast_ok = (
        len(fast_clean_tokens) >= 2
        or len(fast_model_lines) >= 1
        or len(normalize_text(fast_text)) >= 80
    )

    if fast_ok:
        return fast_text, "fast"

    deep_text = run_ocr_regions(img, deep_regions, mode="deep")
    merged = "\n".join(unique_keep_order([fast_text, deep_text]))
    return merged, "deep"


async def build_evidence_from_upload(file) -> Dict[str, Any]:
    content = await file.read()

    try:
        original_img = Image.open(BytesIO(content)).convert("RGB")
        original_width, original_height = original_img.size
        img = prepare_image_for_processing(original_img)
    except Exception as e:
        return {
            "success": False,
            "error": f"No se pudo procesar la imagen: {str(e)}",
            "ocrText": "",
            "ocrError": "",
            "cleanTokens": [],
            "strongTokens": [],
            "modelLines": [],
            "yearsDetected": [],
            "imageInfo": {},
            "visualSignals": {},
            "quality": {
                "likelyInsufficient": True,
                "warnings": ["image_processing_error"],
            },
        }

    processed_width, processed_height = img.size
    visual = visual_signals(img)

    try:
        ocr_text, ocr_mode = extract_ocr_text_two_phase(img)
        ocr_error = ""
    except Exception as e:
        ocr_text = ""
        ocr_mode = "error"
        ocr_error = str(e)

    clean_tokens = clean_tokens_from_ocr(ocr_text)
    strong_tokens = strong_ocr_tokens(ocr_text)
    model_lines = extract_model_like_lines(ocr_text)
    years_detected = extract_years(ocr_text)
    quality = evaluate_ocr_quality(
        original_width=original_width,
        original_height=original_height,
        ocr_text=ocr_text,
        clean_tokens=clean_tokens,
        model_lines=model_lines,
    )

    return {
        "success": True,
        "error": "",
        "ocrText": ocr_text[:1000],
        "ocrError": ocr_error,
        "cleanTokens": clean_tokens,
        "strongTokens": strong_tokens,
        "modelLines": model_lines,
        "yearsDetected": years_detected,
        "imageInfo": {
            "width": original_width,
            "height": original_height,
            "processedWidth": processed_width,
            "processedHeight": processed_height,
            "filename": getattr(file, "filename", ""),
            "contentType": getattr(file, "content_type", ""),
        },
        "visualSignals": visual,
        "quality": quality,
        "ocrMode": ocr_mode,
    }
