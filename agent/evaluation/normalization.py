import re
import unicodedata
from functools import lru_cache
from typing import Tuple, Union, Dict, Any

from api.get_ucid import select_best_ucid

KNOWN_CODES = {
    "US","CA","CN","EP","FR","DE","IT","JP","RU","ES","GB","UK","WO","KR","AU",
    "BR","IN","MX","TW","SG","HK","NL","BE","CH","AT","PT","SE","DK","FI","NO",
    "IE","IL","NZ","ZA","PL","CZ","HU","TR","AR","CL","CO","PE","PH","TH","ID",
    "VN","AE","SA","QA","KW","UA","SI","SK","RO","BG","GR","LU","MC","LI",
}

COUNTRY_KEYWORDS = [
    ("UNITED STATES", "US"),
    ("U.S.", "US"),
    ("USA", "US"),
    ("UNITED KINGDOM", "GB"),
    ("GREAT BRITAIN", "GB"),
    ("ENGLAND", "GB"),
    ("CANADA", "CA"),
    ("FRANCE", "FR"),
    ("GERMANY", "DE"),
    ("DEUTSCHLAND", "DE"),
    ("JAPAN", "JP"),
    ("CHINA", "CN"),
    ("KOREA", "KR"),
    ("REPUBLIC OF KOREA", "KR"),
    ("SOUTH KOREA", "KR"),
    ("RUSSIA", "RU"),
    ("RUSSIAN FEDERATION", "RU"),
    ("SPAIN", "ES"),
    ("ITALY", "IT"),
    ("EUROPEAN PATENT", "EP"),
    ("EUROPEAN", "EP"),
    ("AUSTRALIA", "AU"),
    ("BRAZIL", "BR"),
    ("MEXICO", "MX"),
    ("INDIA", "IN"),
]

PATENT_PATTERN = re.compile(
    r"\b([A-Z]{2,3})([A-Z])?[-\s/]*((?:\d[\d\s,./-]*)\d)(?:\s*[A-Z]\d?)?",
    flags=re.IGNORECASE,
)

PRODUCT_KEYS = (
    "normalized_product",
    "normalized_name",
    "product",
    "product_name",
    "productName",
    "name",
    "title",
    "value",
    "label",
)


def normalize_text(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _stringify_list(values) -> str:
    return " ".join(str(v or "").strip() for v in values if v)


def _extract_product_text(prod: Union[str, Dict[str, Any], list, tuple, None]) -> str:
    if prod is None:
        return ""
    if isinstance(prod, dict):
        for key in PRODUCT_KEYS:
            if key in prod and prod[key]:
                val = prod[key]
                if isinstance(val, (list, tuple, set)):
                    return _stringify_list(val)
                return str(val)
    if isinstance(prod, (list, tuple, set)):
        return _stringify_list(prod)
    return str(prod)


def normalize_prod(prod: Union[str, Dict[str, Any], list, tuple, None]) -> str:
    """
    Normalise un nom de produit en supprimant la casse, les marques et les espaces superflus.
    """
    raw = _extract_product_text(prod)
    if not raw:
        return ""
    cleaned = raw.replace("™", " ").replace("®", " ").replace("©", " ")
    text = unicodedata.normalize("NFKC", cleaned)
    text = text.replace("&", " and ")
    text = re.sub(r"[^0-9A-Za-z ]+", " ", text)
    normalized = normalize_text(text)
    tokens = [tok for tok in normalized.split() if tok not in {"tm", "r", "c"}]
    return " ".join(tokens)


def _fix_code(code: str | None) -> str:
    if not code:
        return ""
    return "GB" if code.upper() == "UK" else code.upper()


def _extract_country_from_text(text: str) -> str:
    up = text.upper()
    for match in re.finditer(r"\b([A-Z]{2,3})\s*[-/ ]*\d", up):
        cand = _fix_code(match.group(1))
        if cand in KNOWN_CODES:
            return cand
    for keyword, code in COUNTRY_KEYWORDS:
        if keyword in up:
            return code
    return ""


def _extract_patent_hint(p: str) -> Tuple[str, str]:
    s = unicodedata.normalize("NFKC", str(p or "")).upper().strip()
    if not s:
        return "", ""

    # try main regex
    match = PATENT_PATTERN.search(s)
    if match:
        code = _fix_code(match.group(1))
        design = (match.group(2) or "").upper()
        digits = "".join(ch for ch in match.group(3) if ch.isdigit())
        candidate = f"{code}{design}{digits}" if code else f"{design}{digits}"
        return candidate, code

    # fallback digits only
    digits = "".join(re.findall(r"\d+", s))
    if not digits:
        return "", ""

    code = _extract_country_from_text(s)
    candidate = f"{code}{digits}" if code else digits
    return candidate, code


def _pick_from_dict(data: Dict[str, Any], keys: tuple[str, ...], default: str = "") -> str:
    for key in keys:
        val = data.get(key)
        if isinstance(val, (list, tuple)) and val:
            return str(val[0])
        if val:
            return str(val)
    return default


@lru_cache(maxsize=2048)
def _select_best_ucid_cached(num: str, country: str) -> str | None:
    try:
        return select_best_ucid(num, country or "")
    except Exception:
        return None


def normalize_pat(p: Union[Dict[str, Any], str, int, float]) -> str:
    """
    Normalise un identifiant de brevet (dict ou str) en UCID ou candidat nettoyé.
    """
    if isinstance(p, dict):
        raw = (
            p.get("number_raw")
            or p.get("normalized_number")
            or p.get("value_raw")
            or _pick_from_dict(p, ("patent", "patent_number", "patentNumber", "value"), "")
        )
        explicit_country = (p.get("country", "") or "").upper()
    else:
        raw = str(p or "")
        explicit_country = ""

    candidate, inferred = _extract_patent_hint(raw)
    if not candidate:
        return ""

    country = explicit_country or inferred or ""

    ucid = _select_best_ucid_cached(candidate, country.lower())
    return ucid or candidate


__all__ = ["normalize_prod", "normalize_pat"]
