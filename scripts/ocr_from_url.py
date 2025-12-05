#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import requests
import traceback

try:
    from pdf2image import convert_from_path
except Exception:  # pragma: no cover - optional dependency
    convert_from_path = None

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None


# -----------------------------
# Helpers
# -----------------------------

def _normalize_tesseract_lang(lang: str | None) -> str:
    """Map shortcuts like 'en' or 'en+fr' to Tesseract language codes."""
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


def download_pdf_to_tmp(url: str) -> str:
    """Télécharge un PDF depuis une URL et le sauvegarde dans un fichier temporaire."""
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(r.content)
    tmp.close()
    return tmp.name


def ocr_pdf_fast(pdf_path: str, lang: str = "en", dpi: int = 200) -> list[str]:
    """
    OCR rapide d’un PDF local → retourne liste de pages textuelles.
    Basé sur pytesseract + pdf2image (Poppler requis).
    """
    if convert_from_path is None:
        raise RuntimeError("pdf2image is not installed; install poppler + pdf2image")
    if pytesseract is None:
        raise RuntimeError("pytesseract is not installed; pip install pytesseract")

    lang_code = _normalize_tesseract_lang(lang)
    pages_out: list[str] = []

    images = convert_from_path(pdf_path, dpi=dpi)
    for idx, img in enumerate(images, 1):
        try:
            text = pytesseract.image_to_string(img, lang=lang_code)
        except Exception as exc:
            print(f"[ERROR] Tesseract on page {idx}: {repr(exc)}", file=sys.stderr)
            continue
        pages_out.append((text or "").strip())

    return pages_out


def ocr_target(target: str, lang: str, dpi: int = 200) -> list[str]:
    """Télécharge (si URL) puis applique l’OCR."""
    target = target.strip()
    if not target:
        return []

    tmp_path = None
    if target.lower().startswith(("http://", "https://")):
        tmp_path = download_pdf_to_tmp(target)
        pdf_path = tmp_path
    else:
        pdf_path = target
        if not Path(pdf_path).is_file():
            raise FileNotFoundError(f"File not found: {pdf_path}")

    try:
        return ocr_pdf_fast(pdf_path, lang=lang, dpi=dpi)
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


# -----------------------------
# CLI
# -----------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="OCR one or more PDF URLs / paths and print pages (pytesseract).")
    ap.add_argument("targets", nargs="+", help="PDF URLs or local file paths")
    ap.add_argument("--lang", default="en", help="OCR language (default: en)")
    ap.add_argument("--out", help="Optional output file to write concatenated pages")
    ap.add_argument("--page-sep", default="\n\n=== PAGE BREAK ===\n\n")
    ap.add_argument("--dpi", type=int, default=200, help="DPI for pdf2image (default: 200)")
    args = ap.parse_args()

    all_pages: list[str] = []

    for t in args.targets:
        print(f"=== OCR: {t} ===")
        try:
            pages = ocr_target(t, lang=args.lang, dpi=args.dpi)
        except Exception as exc:
            print(f"[ERROR] {t}: {repr(exc)}", file=sys.stderr)
            traceback.print_exc()  # affiche la stack trace complète
            return 2

        if not pages:
            print("(no OCR output)")
        else:
            for i, pg in enumerate(pages, 1):
                print(f"\n--- Page {i} ---")
                print(pg.strip())

        all_pages.extend(pages or [])
        print("")

    if args.out:
        out_path = Path(args.out).resolve()
        out_path.write_text(
            args.page_sep.join(p.strip() for p in all_pages if p.strip()),
            encoding="utf-8",
        )
        print(f"[WRITE] Saved merged OCR to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
