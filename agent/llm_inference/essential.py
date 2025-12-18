import hashlib
import json
import re
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse, unquote

from agent.llm.llm_utils import parse_json_lines
from api.get_ucid import select_best_ucid


def filename_from_url(url: str, ext: str = ".ndjson") -> str:
    """
    Build a deterministic, filesystem-safe filename from a URL.
    Includes a short hash of the full URL to avoid collisions.
    """
    parsed = urlparse(url)
    base = Path(parsed.path).name or "document"
    base = unquote(base)

    base = base.strip().replace(" ", "_")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    if not base:
        base = "document"

    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    base_no_ext = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", base)
    return f"{base_no_ext}__{h}{ext}"


def extract_essentials(items: List[dict], mode: str) -> Tuple[List[str], List[str]]:
    """
    Reduce a list of LLM items to essential products/patents depending on mode.
    Returns (products, patents) as sorted lists.
    """
    products: set[str] = set()
    patents: set[str] = set()

    if mode == "full":
        for d in items:
            if not isinstance(d, dict):
                continue
            p = (d.get("product_name") or "").strip()
            if p:
                products.add(p)
            for pat in d.get("patents") or []:
                if isinstance(pat, str):
                    v = pat.strip()
                    if v:
                        patents.add(v.upper())

    elif mode == "products":
        for d in items:
            if not isinstance(d, dict):
                continue
            p = (d.get("product_name") or "").strip()
            if p:
                products.add(p)

    elif mode == "patents":
        for d in items:
            if not isinstance(d, dict):
                continue
            n = (d.get("normalized_number") or "").strip()
            if n:
                patents.add(n.upper())

    elif mode == "audit":
        for d in items:
            if not isinstance(d, dict):
                continue
            t = d.get("type")
            if t == "product":
                v = (d.get("value_raw") or "").strip()
                if v:
                    products.add(v)
            elif t == "patent":
                n = (d.get("normalized_number") or "").strip()
                if n:
                    patents.add(n.upper())

    else:
        # Fallback: try to harvest both if present
        for d in items:
            if not isinstance(d, dict):
                continue
            p = (d.get("product_name") or "").strip()
            if p:
                products.add(p)
            n = (d.get("normalized_number") or "").strip()
            if n:
                patents.add(n.upper())

    return sorted(products), sorted(patents)


def essentials_from_raw(raw_output: str, mode: str) -> Tuple[List[str], List[str]]:
    """Parse raw NDJSON/text into items then extract essentials."""
    items = parse_json_lines(raw_output)
    return extract_essentials(items, mode)


def write_essential(path: Path, source_url: str, products: List[str], patents: List[str]) -> Path:
    """Write a single-line NDJSON with source/products/patents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source_url,
        "products": products,
        "patents": patents,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def resolve_patents_with_api(patents: List[str]) -> List[str]:
    """
    Try to resolve patents to UCID via patents.google.com API.
    Fallback to original number if API fails or returns nothing.
    """
    resolved: list[str] = []
    for pat in patents:
        if not pat:
            continue
        country = pat[:2] if len(pat) >= 2 else ""
        ucid = None
        try:
            ucid = select_best_ucid(pat, country)
        except Exception:
            ucid = None
        resolved.append(ucid or pat)
    # keep deterministic order, remove duplicates while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for p in resolved:
        if p not in seen:
            unique.append(p)
            seen.add(p)
    return unique


__all__ = [
    "filename_from_url",
    "extract_essentials",
    "essentials_from_raw",
    "write_essential",
    "resolve_patents_with_api",
]
