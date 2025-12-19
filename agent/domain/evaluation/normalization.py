"""
Patent normalization utilities for ProductInfo-AI.

This module provides:
    - normalize_pat : deterministic UCID-like cleanup
    - canonicalize_for_eval : evaluation-only canonicalization
"""

from __future__ import annotations
import re


# ----------------------------------------------------------------------
# Regex simple : CC + digits (+ optional kind like B2, A1, S1…)
# Exemple : US9439375B2, EP1106985, CN2006800266812
# ----------------------------------------------------------------------
PATENT_RE = re.compile(r"^([A-Z]{2})(\d+)([A-Z]\d?)?$")
USD_RE = re.compile(r"^USD(\d+)([A-Z]\d?)?$")


# ----------------------------------------------------------------------
# Minimal deterministic cleanup
# ----------------------------------------------------------------------
def _sanitize_raw(raw: str) -> str:
    """
    Clean a raw patent string into a compact uppercase form:
    - remove parentheses
    - remove any non-alphanumeric chars
    - uppercase letters
    """
    if not raw:
        return ""
    s = raw.upper().strip()

    # Remove text inside parentheses
    s = re.sub(r"\([^)]*\)", "", s)

    # Keep only alphanumerics (removes spaces, hyphens, slashes, commas…)
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s


# ----------------------------------------------------------------------
# Normalisation business principale
# ----------------------------------------------------------------------
def normalize_pat(raw: str) -> str:
    """
    Deterministically normalize a patent string to a UCID-like format.

    Rules:
        - clean the input (remove noise)
        - detect CC + number + optional kind
        - convert Chinese ZL → CN
        - output "CC<number><kind>" or the cleaned string if unrecognized

    Examples:
        "US 9,439,375 B2"   → "US9439375B2"
        "ZL200680026681.2"  → "CN2006800266812"
        "EP1106985"         → "EP1106985"
    """
    if not raw:
        return ""
    if isinstance(raw, dict):
        # try the common keys the LLM returns
        raw = (
            raw.get("normalized_number")
            or raw.get("patent")
            or raw.get("patent_number")
            or raw.get("patentNumber")
            or raw.get("number_raw")
            or ""
        )
    s = _sanitize_raw(raw)
    if not s:
        return s

    m = PATENT_RE.match(s)
    if not m:
        # Unknown shape → return deterministic cleaned value
        return s

    country, num, kind = m.group(1), m.group(2), m.group(3) or ""

    # Normalize Chinese patents: ZLxxxxxx → CNxxxxxx
    if country == "ZL":
        country = "CN"

    return f"{country}{num}{kind}"


# ----------------------------------------------------------------------
# Canonicalization for evaluation (expected vs predicted)
# ----------------------------------------------------------------------
def canonicalize_for_eval(ucid: str) -> str:
    """
    Canonical form of a UCID for evaluation purposes.

    Rules:
      - Base on normalize_pat()
      - US design patents:
            USD823786A   → USD823786
            USD823786S1  → USD823786
            US823786A    → USD823786  (6 digits or fewer)
      - Other patents (utility, EP, JP, etc.) remain as-is.

    This removes irrelevant suffix differences (A, S1) when comparing
    expected vs predicted patents.
    """
    if not ucid:
        return ucid

    u = normalize_pat(ucid)
    digits = "".join(ch for ch in u if ch.isdigit())

    if not digits:
        return u

    # Already a USD design patent → strip suffix
    if u.startswith("USD"):
        return f"USD{digits}"

    # Some data encode US designs as "US<digits>A", "US<digits>"
    if u.startswith("US") and 1 <= len(digits) <= 6:
        return f"USD{digits}"

    return u


def standard_pat_key(raw: str) -> str | None:
    """
    Return a standard comparison key, or None if not a plausible patent.

    Examples:
      US10277158B2 -> US10277158
      CN107076464A -> CN107076464
      US823786S1   -> USD823786
      USD823786S1  -> USD823786
      USD1004141   -> USD1004141
      COMPMOUNT... -> None
    """
    if not raw:
        return None

    s = _sanitize_raw(raw)
    if not s:
        return None

    # 1) USD designs: USD<digits>(kind?) -> USD<digits>
    m_usd = USD_RE.match(s)
    if m_usd:
        num = m_usd.group(1)
        return f"USD{num}"

    # 2) Normal CC<digits>(kind?)
    m = PATENT_RE.match(s)
    if not m:
        return None  # filters OCR garbage

    country, num, kind = m.group(1), m.group(2), (m.group(3) or "")

    if country == "ZL":
        country = "CN"
        
    # 4) Default: drop kind suffix
    return f"{country}{num}"


__all__ = [
    "normalize_pat",
    "canonicalize_for_eval",
    "standard_pat_key",
    "PATENT_RE",
]
