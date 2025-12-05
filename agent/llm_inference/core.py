"""
Dispatcher central pour les différents modes d’analyse :
- products : extraction des produits
- patents  : extraction des brevets
- audit    : vérification OCR seule
- full     : pipeline complet (produits + brevets + mapping + audit)
"""

import asyncio
import os
import sys
from typing import List

from agent.llm_inference.modes import (
    analyse_url_products,
    analyse_url_patents,
    analyse_url_audit,
    analyse_url_columns,
)

USE_OCR = os.getenv("USE_OCR", "0") == "1"


def log(msg: str):
    """Print uniforme sur stderr."""
    print(msg, file=sys.stderr, flush=True)


# ------------------------------------------------------------
# Point d’entrée unique
# ------------------------------------------------------------

async def analyse_url(url: str, mode: str) -> str:
    """
    Analyse un document PDF/HTML selon le mode choisi :
    - full : pipeline complet (produits + brevets + mapping + audit)
    - audit : audit OCR pur
    - patents : brevets uniquement
    - products : produits uniquement
    """
    log(f"[START] Analyse {url} en mode={mode}")

    if mode == "products":
        return await analyse_url_products(url)

    if mode == "patents":
        return await analyse_url_patents(url)

    if mode == "audit":
        return await analyse_url_audit(url)

    if mode == "full":
        return await analyse_url_columns(url)

    raise ValueError(f"Mode inconnu : {mode!r}. Choisis parmi 'products', 'patents', 'audit', 'full'.")


# ------------------------------------------------------------
# Analyse de plusieurs documents (batch)
# ------------------------------------------------------------

async def analyse_many_urls(urls: List[str], *, max_concurrency: int = 4, mode: str = "full") -> List[dict]:
    """
    Analyse plusieurs documents en parallèle.
    Chaque tâche est limitée par un sémaphore de max_concurrency.
    Retourne une liste de dictionnaires : {url, ok, output|error}.
    """
    sem = asyncio.Semaphore(max_concurrency)
    log(f"[BATCH] {len(urls)} documents à traiter en mode={mode}")

    async def one(u: str):
        async with sem:
            try:
                out = await analyse_url(u, mode)
                return {"url": u, "ok": True, "output": out}
            except Exception as e:
                log(f"[ERREUR] {u}: {e}")
                return {"url": u, "ok": False, "error": str(e)}

    return await asyncio.gather(*(one(u) for u in urls))
