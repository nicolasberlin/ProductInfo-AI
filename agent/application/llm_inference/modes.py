import asyncio
import difflib
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List

from agent.domain.evaluation.normalization import normalize_pat
from agent.infrastructure.llm.llm_calls import (
    send_patent_token_json,
    send_product_names,
    send_verification_audit,
    send_mapping_products_patents,
    send_group_mappings_by_product,
)
from agent.infrastructure.llm.llm_utils import (
    _download_pdf_to_tmp,
    _ocr_pdf_to_pages,
    _ocr_images_to_pages,
    _render_html_to_png,
    _looks_like_pdf,
    parse_json_lines,
    normalize_pages,
    to_jsonl,
)
from agent.infrastructure.preprocess.extractor import fetch_text_pages


def log(msg: str, *, mode: str | None = None, run: str | None = None, ocr: str | None = None, src: str | None = None):
    """Uniform stderr logging with optional prefixes."""
    prefix = []
    if mode:
        prefix.append(f"MODE={mode}")
    if run:
        prefix.append(f"RUN={run}")
    if ocr:
        prefix.append(f"OCR={ocr}")
    if src:
        prefix.append(f"SRC={src}")
    pre = "[" + "][".join(prefix) + "] " if prefix else ""
    print(pre + msg, file=sys.stderr, flush=True)


# ------------------------------------------------------------
# OCR configuration (source of truth: USE_OCR)
# ------------------------------------------------------------

def set_use_ocr(enabled: bool) -> None:
    """Set USE_OCR in env for this process. True -> USE_OCR=1, False -> USE_OCR=0."""
    os.environ["USE_OCR"] = "1" if enabled else "0"


def use_ocr() -> bool:
    """Return OCR state from environment (USE_OCR, default=1)."""
    return os.getenv("USE_OCR", "1") == "1"


@contextmanager
def _temporary_ocr_env(enabled: bool):
    """Ensure USE_OCR matches the requested mode, then restore."""
    prev = os.environ.get("USE_OCR")
    os.environ["USE_OCR"] = "1" if enabled else "0"
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("USE_OCR", None)
        else:
            os.environ["USE_OCR"] = prev


# Possible product keys in LLM JSON
PRODUCT_KEYS = (
    "product_name",
    "product",
    "productName",
    "name",
    "title",
    "normalized_product",
    "normalized_name",
    "label",
    "value",
)


def _normalize_product_token(value) -> str:
    """Normalize a product name for comparison (lowercase + compact spaces)."""
    if value is None:
        return ""
    text = " ".join(str(value).split()).strip()
    return text.lower()


def _iter_product_values(obj: dict):
    """Iterate over possible product values in an LLM dict."""
    for key in PRODUCT_KEYS:
        if key not in obj:
            continue
        val = obj[key]
        if isinstance(val, (list, tuple, set)):
            for v in val:
                yield v
        else:
            yield val


def _extract_product_set(out: str) -> set[str]:
    """Build a normalized product set from LLM JSONL output."""
    products: set[str] = set()
    for d in parse_json_lines(out):
        if not isinstance(d, dict):
            continue
        for v in _iter_product_values(d):
            norm = _normalize_product_token(v)
            if norm:
                products.add(norm)
    return products


def _extract_patent_set(out: str) -> set[str]:
    """Build a normalized patent set from LLM JSONL output."""
    patents: set[str] = set()
    normalized = _normalize_llm_patent_lines(out)
    for d in parse_json_lines(normalized):
        if not isinstance(d, dict):
            continue
        num = (d.get("normalized_number") or "").upper()
        if num:
            patents.add(num)
    return patents


def _log_ocr_diff(base_set: set[str], ocr_set: set[str], *, mode: str, label: str):
    """Log differences between run A (no OCR) and run B (with OCR)."""
    additions = sorted(ocr_set - base_set)
    removed = sorted(base_set - ocr_set)
    log(
        f"[OCR-CHECK][{label}] A (no OCR)={len(base_set)} | B (with OCR)={len(ocr_set)} | +OCR={len(additions)} | -OCR={len(removed)}",
        mode=mode,
    )
    if additions or removed:
        if additions:
            log(f"[WARN][OCR][{label}] Added with OCR (B - A): {', '.join(additions)}", mode=mode)
        if removed:
            log(f"[WARN][OCR][{label}] Removed when OCR enabled (A - B): {', '.join(removed)}", mode=mode)
    else:
        log(f"[OCR-CHECK][{label}] No difference between final sets (A vs B)", mode=mode)
    return additions, removed


def _start_label(url: str) -> str:
    """START message with URL only when LOG_URL_START=1."""
    if os.getenv("LOG_URL_START", "0") == "1":
        return f"START url={url}"
    return "START"


async def safe_call(coro, name: str):
    """Execute a coroutine without breaking the pipeline if it fails."""
    try:
        return await coro
    except Exception as e:
        log(f"[ERROR] {name}: {e}")
        return ""


def _should_run_ocr(url: str) -> bool:
    """Decide if OCR should be attempted (PDF or renderable HTML)."""
    if not use_ocr():
        return False
    if not url:
        return False
    if _looks_like_pdf(url):
        return True
    if url.lower().startswith(("http://", "https://", "file://")):
        return True
    return os.path.exists(url)


def _log_ocr_html_diff(native_pages: list[str], ocr_pages: list[str], url: str, *, mode: str | None = None, run: str | None = None, ocr_state: str | None = None, src: str | None = None) -> None:
    """Warn if OCR HTML diverges significantly from native text. Applies to HTML only."""
    if ocr_state != "on":
        return
    if not ocr_pages or not native_pages:
        return
    if _looks_like_pdf(url):
        return
    native = "\n\n".join(normalize_pages(native_pages))
    ocr = "\n\n".join(normalize_pages(ocr_pages))
    if not native or not ocr:
        return
    ratio = difflib.SequenceMatcher(None, native, ocr).ratio()
    if ratio < 0.98:
        log(f"[WARN][OCR-HTML] Native vs OCR divergence (similarity={ratio:.2f}, native={len(native)} chars, ocr={len(ocr)} chars)", mode=mode, run=run, ocr=ocr_state, src=src)


def _maybe_dump_ocr_pages(pages: list[str], *, mode: str, run: str, src: str):
    # DEBUG TEMP: dump OCR HTML text for inspection (remove when finished)
    if os.getenv("DEBUG_OCR_HTML", "0") != "1" or not pages:
        return
    for i, pg in enumerate(pages, 1):
        snippet = (pg or "").replace("\n", " ")
        if len(snippet) > 300:
            snippet = snippet[:300] + "…"
        log(f"[DEBUG_OCR_HTML][{i}] {snippet}", mode=mode, run=run, ocr="on", src=src)
    # END DEBUG TEMP


async def _run_ocr_task(url: str) -> list[str]:
    """Async OCR task (PDF or HTML rendered to PNG), run in parallel."""
    try:
        if _looks_like_pdf(url):
            pdf_path = _download_pdf_to_tmp(url) if url.lower().startswith("http") else url
            try:
                return _ocr_pdf_to_pages(pdf_path, lang="en") or []
            finally:
                if url.lower().startswith("http"):
                    Path(pdf_path).unlink(missing_ok=True)

        with tempfile.TemporaryDirectory(prefix="html_ocr_") as tmpdir:
            images = await _render_html_to_png(url, out_dir=tmpdir)
            if not images:
                return []
            return _ocr_images_to_pages(images, lang="en") or []
    except Exception as e:
        log(f"[OCR] OCR failure: {e}")
        return []


# ------------------------------------------------------------
# MODE 1 — Products only
# ------------------------------------------------------------

async def _extract_products_once(url: str, enable_ocr: bool, run_label: str) -> tuple[str, set[str]]:
    """Run product extraction (with or without OCR) and return (output, product set)."""
    src = "pdf" if _looks_like_pdf(url) else "html"
    mode = "products"
    start = time.perf_counter()
    with _temporary_ocr_env(enable_ocr):
        log(_start_label(url), mode=mode, run=run_label, ocr="on" if enable_ocr else "off", src=src)

        # Launch OCR and text extraction in parallel
        pages_task = asyncio.to_thread(fetch_text_pages, url)
        ocr_task = asyncio.create_task(_run_ocr_task(url)) if enable_ocr and _should_run_ocr(url) else None

        pages = normalize_pages(await pages_task)
        results = await asyncio.gather(*(send_product_names(p) for p in pages))
        out = "\n".join(results)

        # Parallel OCR completes here
        ocr_pages = normalize_pages(await ocr_task) if ocr_task else []
        _maybe_dump_ocr_pages(ocr_pages, mode=mode, run=run_label, src=src)
        _log_ocr_html_diff(pages, ocr_pages, url, mode=mode, run=run_label, ocr_state="on" if enable_ocr else "off", src=src)
        full_text = "\n\n".join(pages)
        ocr_text = "\n\n".join(ocr_pages or [])

        audit_added: list[str] = []
        if enable_ocr and ocr_pages:
            try:
                audit = await send_verification_audit(out or "", "", ocr_text or full_text)
                if audit:
                    audit_items = parse_json_lines(audit)
                    ocr_additions = [
                        a for a in audit_items
                        if a.get("type") == "product" and a.get("confidence", 0) > 0.7
                    ]
                    new_items = []
                    for a in ocr_additions:
                        norm = _normalize_product_token(a.get("value_raw"))
                        if not norm or norm in audit_added:
                            continue
                        audit_added.append(norm)
                        new_items.append(json.dumps({
                            "product_name": a.get("value_raw", ""),
                            "confidence": a.get("confidence", 0),
                            "source": "audit",
                        }))
                    if new_items:
                        out = "\n".join([out, *new_items])
                        log(f"[VERIFY products] +{len(new_items)} products added from OCR", mode=mode, run=run_label, ocr="on", src=src)
            except Exception as e:
                log(f"[VERIFY products] audit error: {e}", mode=mode, run=run_label, ocr="on", src=src)
        elif enable_ocr:
            log("OCR requested but no OCR pages (empty capture/OCR)", mode=mode, run=run_label, ocr="on", src=src)

        product_set = _extract_product_set(out)
        elapsed = time.perf_counter() - start
        log(f"DONE pages={len(pages)} ocr_pages={len(ocr_pages)} products={len(product_set)} audit_add={len(audit_added)} time={elapsed:.1f}s", mode=mode, run=run_label, ocr="on" if enable_ocr else "off", src=src)
        return out, product_set


async def analyse_url_products(url: str) -> str:
    """Product extraction with OCR comparison (A without OCR, B with OCR if enabled)."""
    log("[MODE] Products only")

    out_no_ocr, products_no_ocr = await _extract_products_once(url, enable_ocr=False, run_label="A")

    if not use_ocr():
        log("[OCR] USE_OCR=0 → OCR comparison disabled, returning non-OCR output", mode="products")
        return out_no_ocr

    out_with_ocr, products_with_ocr = await _extract_products_once(url, enable_ocr=True, run_label="B")
    _log_ocr_diff(products_no_ocr, products_with_ocr, mode="products", label="products")

    # By default, return OCR output (run B)
    return out_with_ocr


# ------------------------------------------------------------
# MODE 2 — Brevets uniquement
# ------------------------------------------------------------
def _normalize_llm_patent_lines(out: str) -> str:
    """Parse each JSON line from the LLM and re-normalize with normalize_pat()."""
    new_lines = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue  # ignore invalid lines

        if not isinstance(d, dict):
            continue

        normalized = normalize_pat(d)  # <--- appel central
        d["normalized_number"] = normalized.upper()

        new_lines.append(json.dumps(d, ensure_ascii=False))
    return "\n".join(new_lines)

async def _extract_patents_once(url: str, enable_ocr: bool, run_label: str) -> tuple[str, List[str]]:
    """
    Run full patent extraction for a given OCR mode.
    Returns (output_jsonl, list_of_normalized_patents).
    """
    src = "pdf" if _looks_like_pdf(url) else "html"
    mode = "patents"
    start = time.perf_counter()

    with _temporary_ocr_env(enable_ocr):
        log(_start_label(url), mode=mode, run=run_label, ocr="on" if enable_ocr else "off", src=src)
        pages_task = asyncio.to_thread(fetch_text_pages, url)
        ocr_task = asyncio.create_task(_run_ocr_task(url)) if enable_ocr and _should_run_ocr(url) else None

        pages = normalize_pages(await pages_task)
        results = await asyncio.gather(*(send_patent_token_json(p) for p in pages))
        out = "\n".join(results)
        out = _normalize_llm_patent_lines(out)

        ocr_pages = normalize_pages(await ocr_task) if ocr_task else []
        full_text = "\n\n".join(pages)
        ocr_text = "\n\n".join(ocr_pages or [])
        _maybe_dump_ocr_pages(ocr_pages, mode=mode, run=run_label, src=src)
        _log_ocr_html_diff(pages, ocr_pages, url, mode=mode, run=run_label, ocr_state="on" if enable_ocr else "off", src=src)

        audit_added: list[str] = []
        if enable_ocr and ocr_pages:
            log(f"OCR pages={len(ocr_pages)}", mode=mode, run=run_label, ocr="on", src=src)
            try:
                audit = await send_verification_audit("", out or "", ocr_text or full_text)
                if audit:
                    audit_items = parse_json_lines(audit)
                    existing = {d.get("normalized_number", "").upper() for d in parse_json_lines(out) if isinstance(d, dict)}
                    new_items = []
                    new_numbers: list[str] = []
                    for a in audit_items:
                        if a.get("type") != "patent" or a.get("confidence", 0) < 0.7:
                            continue
                        num = (a.get("normalized_number") or "").upper()
                        if not num:
                            num = normalize_pat({"number_raw": a.get("value_raw", "")}).upper()
                        if not num or num in existing or num in new_numbers:
                            continue
                        new_numbers.append(num)
                        new_items.append(json.dumps({
                            "number_raw": a.get("value_raw", ""),
                            "normalized_number": num,
                            "confidence": a.get("confidence", 0),
                            "source": "audit",
                        }))
                    if new_items:
                        out = "\n".join([out, *new_items])
                        audit_added = new_numbers
                        log(f"[VERIFY] +{len(new_items)} patents via OCR audit: {', '.join(new_numbers)}", mode=mode, run=run_label, ocr="on", src=src)
            except Exception as e:
                log(f"[VERIFY] audit error: {e}", mode=mode, run=run_label, ocr="on", src=src)
        elif enable_ocr:
            log("OCR requested but no OCR pages (empty capture/OCR)", mode=mode, run=run_label, ocr="on", src=src)

        final_out = _normalize_llm_patent_lines(out)
        patent_set = sorted({
            (d.get("normalized_number") or "").upper()
            for d in parse_json_lines(final_out)
            if isinstance(d, dict) and d.get("normalized_number")
        })
        elapsed = time.perf_counter() - start
        log(f"DONE pages={len(pages)} ocr_pages={len(ocr_pages)} patents={len(patent_set)} audit_add={len(audit_added)} time={elapsed:.1f}s", mode=mode, run=run_label, ocr="on" if enable_ocr else "off", src=src)
        return final_out, patent_set

async def analyse_url_patents(url: str) -> str:
    """
    Patent extraction with OCR comparison:
    - Run A: without OCR
    - Run B: with OCR (only if USE_OCR=1)
    Compares normalized final sets (not intermediates).
    """
    log("[MODE] Patents only")

    run_ocr = use_ocr()
    out_no_ocr, patents_no_ocr = await _extract_patents_once(url, enable_ocr=False, run_label="A")

    if not run_ocr:
        log("[OCR] USE_OCR=0 → OCR comparison disabled, returning non-OCR output")
        return out_no_ocr

    out_with_ocr, patents_with_ocr = await _extract_patents_once(url, enable_ocr=True, run_label="B")

    base_set = set(patents_no_ocr)
    ocr_set = set(patents_with_ocr)
    additions = sorted(ocr_set - base_set)
    removed = sorted(base_set - ocr_set)

    log(f"[OCR-CHECK] A (no OCR)={len(base_set)} | B (with OCR)={len(ocr_set)} | +OCR={len(additions)} | -OCR={len(removed)}", mode="patents")
    if additions or removed:
        if additions:
            log(f"[WARN][OCR] Added with OCR (B - A): {', '.join(additions)}", mode="patents")
        if removed:
            log(f"[WARN][OCR] Removed when OCR enabled (A - B): {', '.join(removed)}", mode="patents")
    else:
        log("[OCR-CHECK] No difference between final sets (A vs B)", mode="patents")

    # By default, return OCR output (run B)
    return out_with_ocr



# ------------------------------------------------------------
# MODE 3 — OCR audit only
# ------------------------------------------------------------

async def _extract_audit_once(url: str, enable_ocr: bool, run_label: str) -> tuple[str, set[str]]:
    """Run OCR audit (with/without OCR) and return (audit_jsonl, normalized set)."""
    src = "pdf" if _looks_like_pdf(url) else "html"
    mode = "audit"
    start = time.perf_counter()
    with _temporary_ocr_env(enable_ocr):
        log(_start_label(url), mode=mode, run=run_label, ocr="on" if enable_ocr else "off", src=src)

        pages_task = asyncio.to_thread(fetch_text_pages, url)
        ocr_task = asyncio.create_task(_run_ocr_task(url)) if enable_ocr and _should_run_ocr(url) else None

        pages = normalize_pages(await pages_task)
        ocr_pages = normalize_pages(await ocr_task) if ocr_task else []
        _maybe_dump_ocr_pages(ocr_pages, mode=mode, run=run_label, src=src)
        _log_ocr_html_diff(pages, ocr_pages, url, mode=mode, run=run_label, ocr_state="on" if enable_ocr else "off", src=src)

        full_text = "\n\n".join(pages)
        ocr_text = "\n\n".join(ocr_pages or [])
        products = await send_product_names(full_text)
        patents = await send_patent_token_json(full_text)

        audit_source = ocr_text or full_text
        audit = await send_verification_audit(products, patents, audit_source) or ""
        audit_set = {json.dumps(obj, sort_keys=True) for obj in parse_json_lines(audit) if isinstance(obj, dict)}
        if audit:
            log(f"[AUDIT] {len(audit.splitlines())} items detected", mode=mode, run=run_label, ocr="on" if enable_ocr else "off", src=src)
        elif enable_ocr:
            log("OCR requested but no OCR pages (empty capture/OCR)", mode=mode, run=run_label, ocr="on", src=src)

        elapsed = time.perf_counter() - start
        log(f"DONE pages={len(pages)} ocr_pages={len(ocr_pages)} audit_items={len(audit_set)} time={elapsed:.1f}s", mode=mode, run=run_label, ocr="on" if enable_ocr else "off", src=src)
        return audit, audit_set


async def analyse_url_audit(url: str) -> str:
    """Compare extracted products/patents vs OCR text (A/B run)."""
    log("[MODE] OCR audit")

    audit_no_ocr, set_no_ocr = await _extract_audit_once(url, enable_ocr=False, run_label="A")
    if not use_ocr():
        log("[OCR] USE_OCR=0 → OCR comparison disabled, returning non-OCR output", mode="audit")
        return audit_no_ocr

    audit_with_ocr, set_with_ocr = await _extract_audit_once(url, enable_ocr=True, run_label="B")
    _log_ocr_diff(set_no_ocr, set_with_ocr, mode="audit", label="audit")

    return audit_with_ocr


# ------------------------------------------------------------
# MODE 4 — Full pipeline (products + patents + mapping + audit)
# ------------------------------------------------------------

async def _extract_columns_once(url: str, enable_ocr: bool, run_label: str) -> tuple[str, set[str], set[str]]:
    """Full pipeline (with/without OCR) → returns (output, product set, patent set)."""
    src = "pdf" if _looks_like_pdf(url) else "html"
    mode = "full"
    start = time.perf_counter()
    with _temporary_ocr_env(enable_ocr):
        log(_start_label(url), mode=mode, run=run_label, ocr="on" if enable_ocr else "off", src=src)

        pages_task = asyncio.to_thread(fetch_text_pages, url)
        ocr_task = asyncio.create_task(_run_ocr_task(url)) if enable_ocr and _should_run_ocr(url) else None

        pages = normalize_pages(await pages_task)
        document_text = [p for p in pages if p.strip()]
        if not document_text:
            if ocr_task:
                await ocr_task  # drain task
            log("No text extracted", mode=mode, run=run_label, ocr="on" if enable_ocr else "off", src=src)
            return "", set(), set()

        # --- Per-page extraction ---
        semaphore = asyncio.Semaphore(6)

        async def process_page(idx: int, page_text: str):
            async with semaphore:
                patents_raw, products_raw = await asyncio.gather(
                    safe_call(send_patent_token_json(page_text), f"patents_page_{idx}"),
                    safe_call(send_product_names(page_text), f"products_page_{idx}"),
                )
                patents = [dict(p, page=idx) for p in parse_json_lines(patents_raw)]
                products = [dict(p, page=idx) for p in parse_json_lines(products_raw)]
                return patents, products

        results = await asyncio.gather(*(process_page(i, t) for i, t in enumerate(document_text, 1)))
        all_patents, all_products = [], []
        for patents, products in results:
            all_patents.extend(patents)
            all_products.extend(products)

        products_jsonl = to_jsonl(all_products)
        patents_jsonl = _normalize_llm_patent_lines(to_jsonl(all_patents))
        all_products = [dict(p) for p in parse_json_lines(products_jsonl)]
        all_patents = [dict(p) for p in parse_json_lines(patents_jsonl)]
        full_text = "\n\n".join(document_text)

        # --- Audit OCR ---
        ocr_pages = normalize_pages(await ocr_task) if ocr_task else []
        _maybe_dump_ocr_pages(ocr_pages, mode=mode, run=run_label, src=src)
        _log_ocr_html_diff(document_text, ocr_pages, url, mode=mode, run=run_label, ocr_state="on" if enable_ocr else "off", src=src)

        audit_added_products: list[str] = []
        audit_added_patents: list[str] = []
        if enable_ocr and ocr_pages:
            audit_source = "\n\n".join(ocr_pages or document_text)
            audit = await safe_call(send_verification_audit(products_jsonl, patents_jsonl, audit_source), "audit")
            if audit:
                audit_items = parse_json_lines(audit)
                existing_products = _extract_product_set(products_jsonl)
                existing_patents = _extract_patent_set(patents_jsonl)

                for a in audit_items:
                    if not isinstance(a, dict) or a.get("confidence", 0) < 0.7:
                        continue
                    if a.get("type") == "product":
                        norm = _normalize_product_token(a.get("value_raw"))
                        if not norm or norm in existing_products:
                            continue
                        existing_products.add(norm)
                        audit_added_products.append(norm)
                        all_products.append({
                            "product_name": a.get("value_raw", ""),
                            "confidence": a.get("confidence", 0),
                            "source": "audit",
                        })
                    elif a.get("type") == "patent":
                        num = (a.get("normalized_number") or "").upper()
                        if not num:
                            num = normalize_pat({"number_raw": a.get("value_raw", "")}).upper()
                        if not num or num in existing_patents:
                            continue
                        existing_patents.add(num)
                        audit_added_patents.append(num)
                        all_patents.append({
                            "number_raw": a.get("value_raw", ""),
                            "normalized_number": num,
                            "confidence": a.get("confidence", 0),
                            "source": "audit",
                        })

                if audit_added_products or audit_added_patents:
                    products_jsonl = to_jsonl(all_products)
                    patents_jsonl = _normalize_llm_patent_lines(to_jsonl(all_patents))
                    log(f"[AUDIT] +{len(audit_added_products)} products / +{len(audit_added_patents)} patents added via OCR", mode=mode, run=run_label, ocr="on", src=src)
        elif enable_ocr:
            log("OCR requested but no OCR pages (empty capture/OCR)", mode=mode, run=run_label, ocr="on", src=src)

        # --- Mapping et grouping ---
        product_set = _extract_product_set(products_jsonl)
        patent_set = _extract_patent_set(patents_jsonl)
        mapping = await safe_call(send_mapping_products_patents(products_jsonl, patents_jsonl, full_text), "mapping")
        grouped = await safe_call(send_group_mappings_by_product(mapping), "grouping")

        elapsed = time.perf_counter() - start
        log(
            f"DONE pages={len(document_text)} ocr_pages={len(ocr_pages)} products={len(product_set)} patents={len(patent_set)} audit_add_prod={len(audit_added_products)} audit_add_pat={len(audit_added_patents)} time={elapsed:.1f}s",
            mode=mode,
            run=run_label,
            ocr="on" if enable_ocr else "off",
            src=src,
        )
        return grouped or mapping, product_set, patent_set


async def analyse_url_columns(url: str) -> str:
    """Full pipeline with OCR comparison (run A without OCR, run B with OCR)."""
    log("[MODE] Full pipeline (full)")

    out_no_ocr, prods_no_ocr, pats_no_ocr = await _extract_columns_once(url, enable_ocr=False, run_label="A")
    if not use_ocr():
        log("[OCR] USE_OCR=0 → OCR comparison disabled, returning non-OCR output", mode="full")
        return out_no_ocr

    out_with_ocr, prods_with_ocr, pats_with_ocr = await _extract_columns_once(url, enable_ocr=True, run_label="B")
    _log_ocr_diff(prods_no_ocr, prods_with_ocr, mode="full", label="products")
    _log_ocr_diff(pats_no_ocr, pats_with_ocr, mode="full", label="patents")

    return out_with_ocr
