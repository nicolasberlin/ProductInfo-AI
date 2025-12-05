import asyncio
import json
import os
import sys
from typing import List

from agent.evaluation.normalization import normalize_pat
from agent.llm.llm_calls import (
    send_patent_token_json,
    send_product_names,
    send_verification_audit,
    send_mapping_products_patents,
    send_group_mappings_by_product,
)
from agent.llm.llm_utils import (
    _download_pdf_to_tmp,
    _ocr_pdf_to_pages,
    parse_json_lines,
    normalize_pages,
    to_jsonl,
)
from agent.preprocess.extractor import fetch_text_pages


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

USE_OCR = os.getenv("USE_OCR", "1") == "1"


def log(msg: str):
    """Print uniforme sur stderr."""
    print(msg, file=sys.stderr, flush=True)


async def safe_call(coro, name: str):
    """Exécute une coroutine sans casser le pipeline si erreur."""
    try:
        return await coro
    except Exception as e:
        log(f"[ERROR] {name}: {e}")
        return ""


async def _run_ocr_task(url: str) -> list[str]:
    """OCR asynchrone, lancé en parallèle."""
    try:
        pdf_path = _download_pdf_to_tmp(url) if url.lower().startswith("http") else url
        return _ocr_pdf_to_pages(pdf_path, lang="en") or []
    except Exception as e:
        log(f"[OCR] Échec OCR : {e}")
        return []


# ------------------------------------------------------------
# MODE 1 — Produits uniquement
# ------------------------------------------------------------

async def analyse_url_products(url: str) -> str:
    """Extraction des produits uniquement, avec OCR parallèle et audit final."""
    log("[MODE] Extraction produits uniquement")

    # Lancement en parallèle : OCR et extraction texte
    pages_task = asyncio.to_thread(fetch_text_pages, url)
    ocr_task = asyncio.create_task(_run_ocr_task(url)) if USE_OCR and url.lower().endswith(".pdf") else None

    pages = normalize_pages(await pages_task)
    results = await asyncio.gather(*(send_product_names(p) for p in pages))
    out = "\n".join(results)

    # OCR parallèle terminé ici
    ocr_pages = normalize_pages(await ocr_task) if ocr_task else []
    full_text = "\n\n".join(pages)
    ocr_text = "\n\n".join(ocr_pages or [])

    # Audit OCR
    try:
        audit = await send_verification_audit(out or "", "", ocr_text or full_text)
        if audit:
            audit_items = parse_json_lines(audit)
            new_items = [
                json.dumps({"product_name": a["value_raw"], "confidence": a["confidence"]})
                for a in audit_items
                if a.get("type") == "product" and a["confidence"] > 0.7
            ]
            if new_items:
                out = "\n".join([out, *new_items])
                log(f"[VERIFY products] +{len(new_items)} produits ajoutés depuis OCR")
    except Exception as e:
        log(f"[VERIFY products] erreur audit : {e}")

    return out


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

async def analyse_url_patents(url: str) -> str:
    """Extraction des brevets uniquement, avec OCR parallèle et audit final."""
    log("[MODE] Extraction brevets uniquement")

    pages_task = asyncio.to_thread(fetch_text_pages, url)
    ocr_task = asyncio.create_task(_run_ocr_task(url)) if USE_OCR and url.lower().endswith(".pdf") else None

    pages = normalize_pages(await pages_task)
    results = await asyncio.gather(*(send_patent_token_json(p) for p in pages))
    out = "\n".join(results)
    out = _normalize_llm_patent_lines(out)


    ocr_pages = normalize_pages(await ocr_task) if ocr_task else []
    full_text = "\n\n".join(pages)
    ocr_text = "\n\n".join(ocr_pages or [])

    # Audit OCR
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
                log(f"[VERIFY patents] +{len(new_items)} brevets ajoutés depuis OCR")
                log(f"[VERIFY patents] détails OCR : {', '.join(new_numbers)}")
    except Exception as e:
        log(f"[VERIFY patents] erreur audit : {e}")

    return _normalize_llm_patent_lines(out)



# ------------------------------------------------------------
# MODE 3 — Audit OCR pur
# ------------------------------------------------------------

async def analyse_url_audit(url: str) -> str:
    """Compare produits et brevets extraits vs texte OCR."""
    log("[MODE] Audit OCR")

    pages_task = asyncio.to_thread(fetch_text_pages, url)
    ocr_task = asyncio.create_task(_run_ocr_task(url)) if USE_OCR and url.lower().endswith(".pdf") else None

    pages = normalize_pages(await pages_task)
    ocr_pages = normalize_pages(await ocr_task) if ocr_task else []

    full_text = "\n\n".join(pages)
    ocr_text = "\n\n".join(ocr_pages or [])
    products = await send_product_names(full_text)
    patents = await send_patent_token_json(full_text)

    audit = await send_verification_audit(products, patents, ocr_text or full_text)
    if audit:
        log(f"[AUDIT] {len(audit.splitlines())} éléments détectés")
    return audit


# ------------------------------------------------------------
# MODE 4 — Pipeline complet (produits + brevets + mapping + audit)
# ------------------------------------------------------------

async def analyse_url_columns(url: str) -> str:
    """Pipeline complet avec OCR parallèle et audit final."""
    log("[MODE] Pipeline complet (full)")

    pages_task = asyncio.to_thread(fetch_text_pages, url)
    ocr_task = asyncio.create_task(_run_ocr_task(url)) if USE_OCR and url.lower().endswith(".pdf") else None

    pages = normalize_pages(await pages_task)
    document_text = [p for p in pages if p.strip()]
    if not document_text:
        return ""

    # --- Extraction par page ---
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
    patents_jsonl = to_jsonl(all_patents)
    full_text = "\n\n".join(document_text)

    # --- Mapping et grouping ---
    mapping = await safe_call(send_mapping_products_patents(products_jsonl, patents_jsonl, full_text), "mapping")
    grouped = await safe_call(send_group_mappings_by_product(mapping), "grouping")

    # --- Audit OCR en parallèle ---
    ocr_pages = normalize_pages(await ocr_task) if ocr_task else []
    audit_source = "\n\n".join(ocr_pages or document_text)
    audit = await safe_call(send_verification_audit(products_jsonl, patents_jsonl, audit_source), "audit")

    if audit:
        log(f"[AUDIT] {len(audit.splitlines())} éléments manquants détectés (OCR={'oui' if ocr_pages else 'non'})")

    return grouped or mapping
