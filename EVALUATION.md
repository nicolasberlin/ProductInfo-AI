# Evaluation (Gold) — ProductInfo-AI

This document explains how we evaluate patent extraction (mode `patents`) from URLs (PDF/web) by comparing pipeline output to versioned “gold” files.

---

## 1) Evaluation goal

Confirm the pipeline captures the patents present in a source (often a PDF):

- **Recall**: no expected patent missing.
- **Precision** (strict mode): no fabricated patent.

This evaluation helps:
- detect regressions (OCR, LLM, parsing, normalization),
- stabilize normalization rules (e.g., USD design patents),
- diagnose errors (missing vs false positives).

---

## 2) Gold data format

Each gold case is defined by two sibling files:

- `case.ndjson`: JSON lines, each with at least a patent field:
  - `patent` or `patent_number`
- `case.url`: the source URL to analyse (PDF/web), single line.

Example (`case.ndjson`):
```json
{"patent":"US 10,277,158 B2"}
{"patent":"US D823,786 S1"}
```

---

## 3) Inference pipeline (LLM + OCR) recap

- CLI entry → `analyse_url` routes to a mode (`products`, `patents`, `audit`, `full`).
- Native text + OCR in parallel: `fetch_text_pages` (PDF/HTML) and `_run_ocr_task` (if `USE_OCR=1` or `--ocr on`).
- Double run A/B: A without OCR, B with OCR; final output is run B and differences are logged.
- LLM per page:
  - products: `send_product_names`
  - patents: `send_patent_token_json`
- Patent normalization: `_normalize_llm_patent_lines` → `normalize_pat` (local, no API) fills `normalized_number` uppercase (ZL→CN, cleaning).
- OCR audit: `send_verification_audit` on OCR (or native) text to add missing products/patents (`source="audit"`).
- Full mode: per-page extraction products+patents, patent normalization, mapping (`send_mapping_products_patents`), grouping (`send_group_mappings_by_product`), then OCR audit to enrich before returning.
