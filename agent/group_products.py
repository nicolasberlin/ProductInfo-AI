import re
from collections import defaultdict

# --- Patterns & normalisation ---
NBSP = "\u00A0"
ZWSP = "\u200B"

# Contrôles/invisibles fréquents dans les PDF
INVISIBLE_RE = re.compile(r'[\x00-\x1F\x7F\u200C-\u200F\u202A-\u202E\u2060\uFEFF]')

# Tirets exotiques → '-'
DASH_MAP = str.maketrans({
    "–": "-", "—": "-", "−": "-", "‒": "-", "―": "-", "-": "-",  # U+2010..U+2015 + U+2011
})

# Patents: US, EP(CC), GB, WO, JP, CN, KR
PATENT_RE = re.compile(
    r'\b(?:US\d{5,}|EP\d+(?:\s*\([A-Z]{2,3}\))?|GB\d{5,}|WO\d{5,}|JP\d{5,}|CN\d{5,}|KR\d{5,})\b'
)

def _clean_line(s: str) -> str:
    s = (s or "")
    # espaces exotiques → espace normal
    s = s.replace(NBSP, " ").replace(ZWSP, " ").replace("\u2009", " ").replace("\u202F", " ").replace("\u3000", " ")
    # ponctuation pleine chasse
    s = s.replace("，", ",").replace("；", ";")
    # tirets exotiques
    s = s.translate(DASH_MAP)
    # parens pays: "( GB )" -> "(GB)"
    s = re.sub(r'\(\s*([A-Za-z]{2,3})\s*\)', r'(\1)', s)
    # marqueurs éventuels
    s = re.sub(r'^\s*LINE:\s*', "", s, flags=re.IGNORECASE)
    s = re.sub(r'\s*END\s*$', "", s, flags=re.IGNORECASE)
    # suppr. contrôles/invisibles
    s = INVISIBLE_RE.sub("", s)
    # espaces multiples
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def _norm_prod(p: str) -> str:
    p = (p or "").translate(DASH_MAP)
    p = re.sub(r'\s+', ' ', p).strip()
    return p

def extract_pairs(text: str) -> dict[str, list[str]]:
    agg = defaultdict(set)
    for raw in text.splitlines():
        line = _clean_line(raw)
        if not line:
            continue

        patents = PATENT_RE.findall(line)
        if not patents:
            continue

        # retire les brevets pour ne garder que les produits
        rest = PATENT_RE.sub("", line)

        # split sur virgule, point-virgule, ou point + espaces
        parts = re.split(r'[;,]|\.\s*', rest)

        for p in parts:
            t = _norm_prod(p)
            if not t:
                continue
            # ignorer tokens pays seuls, ex: "(GB)"
            if re.fullmatch(r'\([A-Z]{2,3}\)', t):
                continue

            for pat in patents:
                agg[t].add(pat.replace(" ", ""))

    return {prod: sorted(pats) for prod, pats in agg.items()}

# --- Tests rapides ---
if __name__ == "__main__":
    # simple
    blob = "US8408056 MEXA-ONE series\nUS9964512 MEXA-ONE series"
    print(extract_pairs(blob))
    # cas PDF "sale" avec contrôle U+0002 entre 0 et 1
    dirty = "US6878940 OBS-2xxx, OBS-ONE GS, MEXA-7xxx, MEXA-ONE series, MEXA-6000 series, MEXA-1170HNDIR, BE-140,BE\u0002150"
    print(extract_pairs(dirty))
