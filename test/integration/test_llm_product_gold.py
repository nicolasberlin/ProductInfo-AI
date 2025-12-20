import asyncio
import json
from pathlib import Path
import sys
import pytest
from rapidfuzz import fuzz

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.application.llm_inference.core import analyse_url
from agent.infrastructure.llm.llm_utils import parse_json_lines
from agent.domain.evaluation.normalization import normalize_prod


# Possible keys containing a product name in LLM output.
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


def _extract_product_fields(obj: dict) -> list[str]:
    """
    Extract all fields that may contain a product name from an LLM dict.
    """
    values = []
    for key in PRODUCT_KEYS:
        if key in obj and obj[key]:
            val = obj[key]

            if isinstance(val, (list, tuple, set)):
                values.extend(str(v) for v in val if v)

            else:
                values.append(str(val))
    return values


def _allow_extras_from_path(path: Path, base_dir: Path) -> bool:
    """Return False for any file under a 'columns' folder."""
    rel_parts = path.relative_to(base_dir).parts
    return "columns" not in rel_parts


def discover_product_cases(base_dir: Path) -> list[tuple[str, str, Path, bool]]:
    """
    Traverse gold data to find:
    - .ndjson (expected products)
    - associated .url files (URL to analyse)
    - allow_extras based on presence of 'columns' in path
    """
    cases = []
    for ndjson_path in base_dir.rglob("*.ndjson"):
        allow_extras = _allow_extras_from_path(ndjson_path, base_dir)
        case_name = ndjson_path.stem
        url_file = ndjson_path.with_suffix(".url")

        if not url_file.exists():
            continue

        url = url_file.read_text().strip()
        if not url:
            continue

        cases.append((case_name, url, ndjson_path, allow_extras))
    return cases


# Prepare parametrized test cases for pytest
GOLD_ROOT = PROJECT_ROOT / "agent" / "domain" / "evaluation" / "gold"
PRODUCT_CASES: list = []
for name, url, gold_path, allow_extras in discover_product_cases(GOLD_ROOT):
    marks = []
    if not allow_extras:
        marks.append(pytest.mark.columns)
    PRODUCT_CASES.append(
        pytest.param(name, url, gold_path, allow_extras, id=name, marks=marks)
    )


def _expected_product_set_from_gold(path: Path) -> set[str]:
    """
    Load gold (ground truth) products from an .ndjson file and normalize for reliable comparison.
    Empty lines, comments, or non-dict JSON are ignored.
    """
    expected: set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("//", "#")):
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(obj, dict):
                continue

            # Extraction + normalisation
            for prod_raw in _extract_product_fields(obj):
                norm = normalize_prod(prod_raw)
                if norm:
                    expected.add(norm)

    return expected


def fuzzy_in(item: str, candidates: set[str], threshold: int = 90) -> bool:
    """
    Fuzzy test: True if item is similar to any element of the set (tolerates minor LLM variations).
    """
    for cand in candidates:
        if fuzz.ratio(item, cand) >= threshold:
            return True
    return False


@pytest.mark.slow
@pytest.mark.llm
@pytest.mark.parametrize("case_name, url, gold_path, allow_extras", PRODUCT_CASES)
def test_llm_product_coverage_all_gold(case_name: str, url: str, gold_path: Path, allow_extras: bool):
    """
    Main test:
      1. Load gold products
      2. Call the LLM agent on the URL
      3. Extract + normalize predicted products
      4. Compare gold vs LLM (fuzzy)
      5. Fail if missing or unexpected products (depending on rules)
    """

    expected = _expected_product_set_from_gold(gold_path)
    assert expected, f"Gold {case_name} empty or missing ({gold_path})."

    raw = asyncio.run(analyse_url(url, mode="products"))
    assert raw, f"Empty extraction for {case_name} ({url})."

    parsed = parse_json_lines(raw)
    print(f"[llm products raw] {parsed}")

    predicted: set[str] = set()
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        for prod_raw in _extract_product_fields(entry):
            norm = normalize_prod(prod_raw)
            if norm:
                predicted.add(norm)

    if predicted:
        print("[llm products normalized]", sorted(predicted))

    missing = {e for e in expected if not fuzzy_in(e, predicted)}
    extra   = {p for p in predicted if not fuzzy_in(p, expected)}

    print(f"{case_name} products: expected={len(expected)} predicted={len(predicted)}")
    if missing:
        print("Missing:", sorted(missing))
    if extra:
        print("Unexpected:", sorted(extra))

    for e in expected:
        scores = [(fuzz.ratio(e, p), p) for p in predicted]
        if not scores:
            continue
        best = max(scores)
        if best[0] < 90:
            print(f"[WARN] Low similarity {best[0]:.1f}% for product '{e}' vs '{best[1]}'")

    assert not missing, f"Missing products {case_name}: {sorted(missing)}"
    if not allow_extras:
        assert not extra, f"Unexpected products {case_name}: {sorted(extra)}"
