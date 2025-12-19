"""
Central dispatcher for the different analysis modes:
- products : extract products only
- patents  : extract patents only
- audit    : OCR-only verification
- full     : full pipeline (products + patents + mapping + audit)
"""

import asyncio
import os
import sys
from typing import List

from agent.application.llm_inference.modes import (
    analyse_url_products,
    analyse_url_patents,
    analyse_url_audit,
    analyse_url_columns,
)

def log(msg: str):
    """Print uniforme sur stderr."""
    print(msg, file=sys.stderr, flush=True)


# ------------------------------------------------------------
# Single entrypoint
# ------------------------------------------------------------

async def analyse_url(url: str, mode: str) -> str:
    """
    Analyse a PDF/HTML document according to the selected mode:
    - full     : full pipeline (products + patents + mapping + audit)
    - audit    : OCR-only audit
    - patents  : patents only
    - products : products only
    """
    log(f"[START] Analyzing {url} mode={mode}")

    if mode == "products":
        return await analyse_url_products(url)

    if mode == "patents":
        return await analyse_url_patents(url)

    if mode == "audit":
        return await analyse_url_audit(url)

    if mode == "full":
        return await analyse_url_columns(url)

    raise ValueError(f"Unknown mode: {mode!r}. Choose among 'products', 'patents', 'audit', 'full'.")


# ------------------------------------------------------------
# Analyse de plusieurs documents (batch)
# ------------------------------------------------------------

async def analyse_many_urls(urls: List[str], *, max_concurrency: int = 24, mode: str = "full") -> List[dict]:
    """
    Analyze several documents in parallel.
    Each task is limited by a max_concurrency semaphore.
    Retourne une liste de dictionnaires : {url, ok, output|error}.
    """
    sem = asyncio.Semaphore(max_concurrency)
    log(f"[BATCH] {len(urls)} documents to process mode={mode}")

    async def one(u: str):
        async with sem:
            try:
                out = await analyse_url(u, mode)
                return {"url": u, "ok": True, "output": out}
            except Exception as e:
                log(f"[ERREUR] {u}: {e}")
                return {"url": u, "ok": False, "error": str(e)}

    return await asyncio.gather(*(one(u) for u in urls))
