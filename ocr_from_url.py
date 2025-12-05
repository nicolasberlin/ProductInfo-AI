#!/usr/bin/env python
"""Convenience wrapper to run OCR from the project root.

Equivalent to: python scripts/ocr_from_url.py <args>
"""
from scripts.ocr_from_url import main

if __name__ == "__main__":
    raise SystemExit(main())
