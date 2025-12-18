#!/usr/bin/env python3
"""
CLI normalizing patents inside NDJSON input.

Usage:
    cat input.ndjson | python api/normalize_patents.py > output.ndjson

Rules:
    1) Local deterministic normalization (normalize_pat)
    2) Optional enrichment via Google Patents API (select_best_ucid)
"""

import sys
import json
import re

from agent.evaluation.normalization import normalize_pat, PATENT_PATTERN as PATENT_RE
from api.get_ucid import select_best_ucid


def normalize_patent(raw_patent: str) -> str:
    """
    Normalize + enrich a patent string:
        - deterministic cleanup (normalize_pat)
        - try resolving a full UCID using Google's API

    If API fails → return the cleaned local form.
    """
    base = normalize_pat(raw_patent)

    m = PATENT_RE.match(base)
    if not m:
        return base

    country, num, _kind = m.group(1), m.group(2), m.group(3) or ""

    try:
        ucid = select_best_ucid(num, country)
    except Exception:
        return base

    return ucid if ucid else base


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        obj = json.loads(line)

        raw = obj.get("patent", "")
        if raw:
            new_pat = normalize_patent(raw)
            # Debug mapping printed on stderr (clean for pipelines)
            try:
                print(f"[normalize] raw='{raw}' -> '{new_pat}'", file=sys.stderr)
            except Exception:
                pass

            obj["patent"] = new_pat

        print(json.dumps(obj, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
