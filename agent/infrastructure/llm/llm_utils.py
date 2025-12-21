import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import List, Union

import requests

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
except Exception:  # pragma: no cover - optional dependency
    async_playwright = None
    PlaywrightTimeoutError = None

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None


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


def _looks_like_pdf(target: str) -> bool:
    """Heuristic to know if the target should be treated as PDF."""
    if not target:
        return False
    lower = target.lower()
    if lower.endswith(".pdf"):
        return True
    if lower.startswith("file://") and lower.endswith(".pdf"):
        return True
    if os.path.exists(target):
        try:
            with open(target, "rb") as f:
                head = f.read(4)
            return head.startswith(b"%PDF")
        except OSError:
            return False
    return False


async def _render_html_to_png(url: str, out_dir: str, wait_ms: int = 1500, timeout_ms: int = 60000) -> list[str]:
    """
    Render a HTML page (remote or local) to a PNG screenshot for OCR.
    Requires playwright with a Chromium browser installed.
    """
    if async_playwright is None:
        log("[OCR][HTML] playwright not installed; HTML capture skipped.")
        return []

    target = url
    if url.startswith("file://"):
        target = url
    elif os.path.exists(url):
        target = Path(url).resolve().as_uri()

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 1800})
            try:
                await page.goto(target, wait_until="networkidle", timeout=timeout_ms)
            except Exception as exc:
                # Retry with a looser condition (domcontentloaded) on timeout only
                if PlaywrightTimeoutError and isinstance(exc, PlaywrightTimeoutError):
                    log(f"[OCR][HTML] networkidle timeout, retry domcontentloaded: {exc}")
                    await page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
                else:
                    raise
            await page.wait_for_timeout(wait_ms)
            out_path = Path(out_dir) / "html_ocr.png"
            await page.screenshot(path=str(out_path), full_page=True)
            await browser.close()
    except Exception as exc:
        log(f"[OCR][HTML] capture failed: {exc}")
        return []

    return [str(out_path)]


def _ocr_pdf_to_pages(pdf_path: str, lang: str = "en", **kwargs):
    # Allow disabling OCR via USE_OCR for testing/performance.
    if os.getenv("USE_OCR", "1") != "1":
        log("[OCR] Disabled via USE_OCR=0; skipping OCR.")
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


def _ocr_images_to_pages(image_paths: list[str], lang: str = "en") -> list[str]:
    """OCR on one or more PNG/JPG images (used for HTML screenshots)."""
    if os.getenv("USE_OCR", "1") != "1":
        log("[OCR] Disabled via USE_OCR=0; skipping OCR.")
        return []
    if pytesseract is None or Image is None:
        log("[OCR] pytesseract or Pillow missing; HTML capture skipped.")
        return []

    lang_code = _normalize_tesseract_lang(lang)
    pages: list[str] = []
    for img_path in image_paths:
        try:
            with Image.open(img_path) as img:
                text = pytesseract.image_to_string(img, lang=lang_code)
        except Exception as exc:
            log(f"[OCR] error on image {img_path}: {exc}")
            continue
        pages.append((text or "").strip())
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
# Page normalization utility
# ------------------------------------------------------------

def normalize_pages(pages: Union[str, List[str], None]) -> List[str]:
    """
    Normalize document text representation:
    - If 'pages' is a string, return [pages]
    - If 'pages' is a list, drop empty pages
    - If 'pages' is None, return []
    """
    if not pages:
        return []
    if isinstance(pages, str):
        pages = [pages]
    return [p.strip() for p in pages if (p or "").strip()]



# ------------------------------------------------------------
# Report writing
# ------------------------------------------------------------

def write_report(result, url, fmt="ndjson"):
    """Write output into agent/reports/"""
    data = parse_json_lines(result)
    reports_dir = Path("agent/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", url.split("/")[-1])
    out_path = reports_dir / f"{slug}.{fmt}"

    if fmt == "json":
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    elif fmt == "tsv":
        keys = sorted({k for d in data for k in d})
        lines = ["\t".join(str(d.get(k, "")) for k in keys) for d in data]
        out_path.write_text("\n".join(lines))
    else:  # default ndjson
        out_path.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in data))

    log(f"[REPORT] Saved to {out_path}")
    return out_path


def to_jsonl(items: list[dict]) -> str:
    return "\n".join(json.dumps(i, ensure_ascii=False) for i in items if i)
