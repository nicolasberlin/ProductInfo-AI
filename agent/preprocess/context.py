import re
from typing import Set

# ---- Détection de contexte (par bloc/section/page) ----
TRIGGERS = {
    "US": r"\b(U\.?S\.?A?\.?|United States)\b.*\bpatent\b",
    "EP": r"\b(European Patent|EP\b|brevet européen)\b",
    "WO": r"\b(PCT|WO\b|international publication)\b",
    "GB": r"\b(UK|United Kingdom|GB\b).*\bpatent\b",
}
def detect_context(text_block: str) -> Set[str]:
    return {code for code, rx in TRIGGERS.items() if re.search(rx, text_block, re.I)}

# ---- Motifs ----
RE_EXPLICIT = re.compile(r"""
\b(?:
  US(?:D|RE|PP)?\s*[0-9][0-9\s,./-]*[0-9][A-Z0-9]* |   # US, USD, USRE, USPP, pubs
  EP\s*[0-9][0-9\s.-]*[0-9](?:\s*[A-Z]\d?)?        |   # EP (+ kind)
  WO\s*(?:\d{4}\s*/\s*\d{5,6}|\d{4}\s*\d{5,6})(?:\s*[A-Z]\d?)? |
  GB\s*\d{5,9}(?:\s*[A-Z]\d?)? |
  JP\s*[\d-]{6,}(?:\s*[A-Z]\d?)? |
  CN\s*\d{7,}(?:\s*[A-Z]\d?)? |
  KR\s*\d{7,}(?:\s*[A-Z]\d?)?
)\b
""", re.I | re.X)

# US implicites (à activer seulement si contexte US détecté)
RE_US_NUM_COMMA = re.compile(r"\b\d{1,3}(?:,\d{3}){1,2}\b")   # ex: 9,122,078

# US implicites (fonctionnent si contexte US détecté)
RE_US_D  = re.compile(r"\bD\s?(?:\d{5,7}|\d{1,3}(?:,\d{3})+)\b", re.I)
RE_US_RE = re.compile(r"\bRE\s?(?:\d{4,6}|\d{1,3}(?:,\d{3})+)\b", re.I)
RE_US_PP = re.compile(r"\bPP\s?(?:\d{4,6}|\d{1,2}(?:,\d{3})+)\b", re.I)

def _digits(s: str) -> str:
    return re.sub(r"[^\d]", "", s)

def _compact(tok: str) -> str:
    t = re.sub(r"\s+", "", tok.upper())
    return t.replace("-", "").replace(".", "").replace(",", "")

def norm_explicit(tok: str) -> str:
    t = _compact(tok)
    # US publication USYYYY/NNNNNNN A1 -> USYYYYNNNNNNNA1
    t = re.sub(r"^(US)(\d{4})/(\d{6,7})([A-Z]\d?)?$", r"\1\2\3\4", t)
    if t.startswith("USD"):   return "USD"  + _digits(t)
    if t.startswith("USRE"):  return "USRE" + _digits(t)
    if t.startswith("USPP"):  return "USPP" + _digits(t)
    if t.startswith("US"):
        m = re.match(r"^US(\d{6,8})([A-Z]\d)?$", t)
        return "US" + (m.group(1) if m else _digits(t)) + (m.group(2) or "")
    if t.startswith("EP"):
        m = re.match(r"^(EP)(\d+)([A-Z]\d)?$", t); 
        return (m.group(1)+m.group(2)+(m.group(3) or "")) if m else "EP"+_digits(t)
    if t.startswith("WO"):
        m = re.match(r"^(WO)(\d{4})(\d{5,6})([A-Z]\d)?$", t)
        if m: return "".join(x for x in m.groups() if x)
        m = re.match(r"^(WO)(\d{4})/(\d{5,6})([A-Z]\d)?$", t)
        return "".join([m.group(1), m.group(2), m.group(3), m.group(4) or ""]) if m else "WO"+re.sub(r"/","",_digits(t))
    if t[:2] in {"GB","JP","CN","KR"}:
        m = re.match(r"^([A-Z]{2})(\d+)([A-Z]\d)?$", t)
        return "".join(x for x in m.groups() if x) if m else t[:2]+_digits(t)
    return t

def norm_us_implicit(tok: str) -> str:
    u = tok.strip().upper()
    if u.startswith("D"):  return "USD"  + _digits(u)
    if u.startswith("RE"): return "USRE" + _digits(u)
    if u.startswith("PP"): return "USPP" + _digits(u)
    return "US" + _digits(u)  # utility

def normalize_text(text: str) -> str:
    """
    Détecte le contexte dans le texte puis normalise les brevets trouvés.
    Retourne le texte normalisé.
    """
    jurisdictions = detect_context(text)        # étape 1
    text = RE_EXPLICIT.sub(lambda m: norm_explicit(m.group(0)), text)  # étape 2
    if "US" in jurisdictions:                   # étape 3 (implicites US)
        for rx in (RE_US_D, RE_US_RE, RE_US_PP, RE_US_NUM_COMMA):
            text = rx.sub(lambda m: norm_us_implicit(m.group(0)), text)
    return text