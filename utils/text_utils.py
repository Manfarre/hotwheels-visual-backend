import re
from difflib import SequenceMatcher
from typing import List


GENERIC_WORDS = {
    "HOT", "WHEELS", "MATTEL", "CLASSICS", "SERIES", "ONE", "CHECKMATE",
    "FOR", "AGES", "OVER", "DIE", "CAST", "METAL", "PLASTIC",
    "ONLINE", "EXCLUSIVE", "COLLECTOR", "COLLECTORS", "MAINLINE", "PREMIUM",
    "CLUB", "REDLINE", "RED", "LINE", "LIMITED", "EDITION", "MODEL",
    "CAR", "CARS", "TOY", "TOYS", "ITEM", "CARD", "CARDED", "LOOSE",
    "THE", "AND", "WITH", "NEW", "COM", "WWW", "HTTP", "HTTPS",
    "SPECIAL", "SEARCH", "WIKI", "FANDOM"
}

NOISE_WORDS = {
    "TIKTOK", "FACEBOOK", "INSTAGRAM", "EBAY", "MERCADO", "GOOGLE",
    "GUARDAR", "COMPARTIR", "DERECHOS", "INFORMACION", "INFORMACIÓN",
    "RESULTADOS", "BUSCAR", "ARTICULO", "ARTÍCULO", "POSIBLE",
    "IMAGENES", "IMÁGENES", "AUTOR", "MAS", "MÁS", "RESPONDER",
    "CHATGPT", "IR", "MENU", "MESSAGE", "MENSAJE", "LIKE", "VIEWS"
}

SERIES_CANDIDATES = [
    "RLC",
    "RED LINE CLUB",
    "PREMIUM",
    "CLASSICS",
    "CHECKMATE",
    "HW SCREEN TIME",
    "BATMAN",
    "SERIES ONE",
    "SERIES 1",
    "MAINLINE",
]


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.upper()
    text = text.replace("\n", " ")
    for ch in [",", ".", ":", ";", "_", "(", ")", "[", "]", "{", "}", "'", '"', "|", "•", "·", "!", "?", "*", "="]:
        text = text.replace(ch, " ")
    text = text.replace("/", " / ")
    text = text.replace("-", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def clean_ocr_lines(ocr_text: str) -> List[str]:
    lines_raw = re.split(r"[\n\r]+", ocr_text or "")
    cleaned = []

    for line in lines_raw:
        line = normalize_text(line)
        if not line:
            continue

        if len(line) <= 1:
            continue

        alpha_count = sum(1 for ch in line if ch.isalpha())
        digit_count = sum(1 for ch in line if ch.isdigit())

        if alpha_count < 2 and digit_count < 2:
            continue

        if any(noise in line for noise in NOISE_WORDS):
            continue

        cleaned.append(line)

    return unique_keep_order(cleaned)


def extract_years(text: str) -> List[str]:
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
    return unique_keep_order(years)


def extract_fractions(text: str) -> List[str]:
    fractions = re.findall(r"\b\d{1,3}\s*/\s*\d{1,3}\b", text)
    normalized = [f.replace(" ", "") for f in fractions]
    return unique_keep_order(normalized)


def extract_series(text: str) -> str:
    t = normalize_text(text)
    for series in SERIES_CANDIDATES:
        if series in t:
            return series
    return ""


def extract_terms(clean_lines: List[str]) -> List[str]:
    tokens = []
    for line in clean_lines:
        for token in line.split():
            if len(token) < 3:
                continue
            if token in GENERIC_WORDS:
                continue
            if token in NOISE_WORDS:
                continue
            if re.fullmatch(r"[0-9/]+", token):
                continue
            tokens.append(token)
    return unique_keep_order(tokens)


def infer_probable_name(joined_text: str) -> str:
    """
    General y estricto:
    solo devuelve una frase si parece nombre de modelo.
    """
    text = normalize_text(joined_text)
    if not text:
        return ""

    tokens = [t for t in text.split() if len(t) >= 3 and t not in NOISE_WORDS]
    if not tokens:
        return ""

    candidates = []
    for size in [4, 3, 2]:
        for i in range(len(tokens) - size + 1):
            phrase = " ".join(tokens[i:i + size]).strip()
            words = phrase.split()

            useful_words = [w for w in words if w not in GENERIC_WORDS and w not in NOISE_WORDS]
            if len(useful_words) < 2:
                continue

            if re.fullmatch(r"[0-9/\- ]+", phrase):
                continue

            candidates.append(phrase)

    candidates = unique_keep_order(candidates)
    if not candidates:
        return ""

    scored = []
    for phrase in candidates:
        words = phrase.split()
        useful_words = [w for w in words if w not in GENERIC_WORDS]
        score = 0.0

        score += len(useful_words) * 1.1
        if len(words) >= 3:
            score += 0.5
        if any(w in {"VOLKSWAGEN", "BEETLE", "BATMOBILE", "BOMB", "BUS", "FORD", "CHEVY"} for w in useful_words):
            score += 1.5
        if any(w in GENERIC_WORDS for w in words):
            score -= 1.0

        scored.append((phrase, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    best_phrase, best_score = scored[0]

    if best_score < 3.0:
        return ""

    return best_phrase
