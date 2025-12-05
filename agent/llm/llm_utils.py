import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import List, Union

import requests


def log(msg: str):
    print(msg, file=sys.stderr, flush=True)


try:
    from pdf2image import convert_from_path
except Exception:
    convert_from_path = None

try:
    import pytesseract
except Exception:
    pytesseract = None


def _download_pdf_to_tmp(url: str) -> str:
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    fd, path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as f:
        f.write(resp.content)
    return path


def _normalize_tesseract_lang(lang: str | None) -> str:
    """
    Map simple language shorthands to Tesseract codes (e.g., en -> eng).
    Allows combos like "en+fr".
    """
    if not lang:
        return "eng"
    cleaned = lang.replace("-", "_").lower().strip()
    if "+" in cleaned:
        return "+".join(_normalize_tesseract_lang(part) for part in cleaned.split("+"))
    mapping = {
        "en": "eng",
        "eng": "eng",
        "english": "eng",
        "fr": "fra",
        "fra": "fra",
        "fre": "fra",
        "french": "fra",
    }
    return mapping.get(cleaned, cleaned)


def _ocr_pdf_to_pages(pdf_path: str, lang: str = "en", **kwargs):
    # Allow disabling OCR via environment flag for testing/performance.
    if os.getenv("DISABLE_OCR") == "1":
        log("[OCR] Disabled via DISABLE_OCR=1; skipping OCR.")
        return []
    if convert_from_path is None:
        log("[OCR] pdf2image is not installed; skipping OCR.")
        return []
    if pytesseract is None:
        log("[OCR] pytesseract is not installed; skipping OCR.")
        return []

    lang_code = _normalize_tesseract_lang(lang)
    dpi = kwargs.get("dpi", 300)
    try:
        imgs = convert_from_path(pdf_path, dpi=dpi)  # requires poppler
    except Exception as exc:
        log(f"[OCR] convert_from_path failed: {exc}")
        return []

    pages: list[str] = []
    for idx, img in enumerate(imgs, 1):
        try:
            text = pytesseract.image_to_string(img, lang=lang_code)
        except Exception as exc:
            log(f"[OCR] pytesseract error on page {idx}: {exc}")
            continue
        pages.append((text or "").strip())

    if os.getenv("DEBUG_OCR", "0") == "1":
        print(f"[OCR] {pdf_path} → {len(pages)} page(s) (Tesseract)", file=sys.stderr)
        for i, page in enumerate(pages or [], 1):
            snippet = (page or "").strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:300] + " …"
            print(f"[OCR][{i}] {snippet}", file=sys.stderr)

    return pages


def parse_json_lines(raw: Union[str, List[str], None]) -> List[dict]:
    """
    Parse JSON Lines or fenced JSON blobs returned by the LLM into a list of dicts.
    Handles:
      - Plain NDJSON (one JSON object per line)
      - JSON arrays / single JSON objects
      - Markdown fenced code blocks (```json ... ```)
      - Bullet prefixes or trailing commas on lines
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        raw = "\n".join(raw)
    if not isinstance(raw, str):
        return []

    text = raw.strip()
    if not text:
        return []

    # Extract fenced code blocks if present, otherwise use the whole text.
    blocks = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if not blocks:
        blocks = [text]

    results: List[dict] = []

    def _ingest(obj):
        if isinstance(obj, dict):
            results.append(obj)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    results.append(item)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # First try to parse the entire block as JSON.
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            _ingest(parsed)
            continue

        # Fallback: treat as NDJSON.
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith(("#", "//")):
                continue
            if line.startswith(("- ", "* ")):
                line = line[2:].strip()
            # Trim stray leading text before JSON object.
            if "{" in line and not line.lstrip().startswith("{"):
                line = line[line.find("{") :]
            line = line.rstrip(",")
            if not line:
                continue
            try:
                parsed_line = json.loads(line)
            except json.JSONDecodeError:
                continue
            _ingest(parsed_line)

    return results



# ------------------------------------------------------------
# Utilitaire : normalisation des pages
# ------------------------------------------------------------

def normalize_pages(pages: Union[str, List[str], None]) -> List[str]:
    """
    Uniformise la représentation du texte du document :
    - Si 'pages' est une chaîne, renvoie [pages]
    - Si 'pages' est une liste, nettoie les pages vides
    - Si 'pages' est None, renvoie []
    """
    if not pages:
        return []
    if isinstance(pages, str):
        pages = [pages]
    return [p.strip() for p in pages if (p or "").strip()]



# ------------------------------------------------------------
# Écriture des rapports
# ------------------------------------------------------------

def write_report(result, url, fmt="ndjson"):
    """Écrit la sortie dans agent/evaluation/reports/"""
    data = parse_json_lines(result)
    reports_dir = Path("agent/evaluation/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", url.split("/")[-1])
    out_path = reports_dir / f"{slug}.{fmt}"

    if fmt == "json":
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    elif fmt == "tsv":
        keys = sorted({k for d in data for k in d})
        lines = ["\t".join(str(d.get(k, "")) for k in keys) for d in data]
        out_path.write_text("\n".join(lines))
    else:  # ndjson par défaut
        out_path.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in data))

    log(f"[REPORT] Enregistré dans {out_path}")
    return out_path


def to_jsonl(items: list[dict]) -> str:
    return "\n".join(json.dumps(i, ensure_ascii=False) for i in items if i)
