import asyncio
import json
from pathlib import Path
import pytest
from rapidfuzz import fuzz
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.domain.evaluation.normalization import canonicalize_for_eval, normalize_pat, standard_pat_key
from agent.infrastructure.llm.llm_utils import parse_json_lines
from agent.application.llm_inference.core import analyse_url



# ----------------------------------------------------------------------
# AUXILIARY DEBUG UTILS
# ----------------------------------------------------------------------
def fuzzy_in(item: str, candidates: set[str], threshold: int = 90) -> bool:
    return any(fuzz.ratio(item, cand) >= threshold for cand in candidates)


def top_matches(x: str, candidates: set[str], k: int = 5):
    scores = [(c, fuzz.ratio(x, c)) for c in candidates]
    scores.sort(key=lambda t: t[1], reverse=True)
    return scores[:k]


# ----------------------------------------------------------------------
# LOAD EXPECTED GOLD
# ----------------------------------------------------------------------
def _expected_patents(path: Path) -> set[str]:
    expected = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            pat = obj.get("patent") or obj.get("patent_number")
            if pat:
                expected.add(normalize_pat(pat))
    return expected


# ----------------------------------------------------------------------
# DISCOVER TEST CASES
# ----------------------------------------------------------------------
def _allow_extras(path: Path, base_dir: Path) -> bool:
    """False si le fichier est dans un sous-dossier 'columns'."""
    parts = path.relative_to(base_dir).parts
    return "columns" not in parts


def discover_cases(base_dir: Path):
    cases = []
    for ndjson in sorted(base_dir.rglob("*.ndjson")):
        url_file = ndjson.with_suffix(".url")
        if not url_file.exists():
            print(f"[WARN] No .url found for {ndjson.name}, skipped.")
            continue

        url = url_file.read_text().strip()
        if not url:
            print(f"[WARN] Empty .url for {ndjson.name}, skipped.")
            continue

        allow_extras = _allow_extras(ndjson, base_dir)
        case_name = ndjson.stem

        marks = []
        if not allow_extras:
            marks.append(pytest.mark.columns)

        cases.append(
            pytest.param(
                case_name, url, ndjson, allow_extras,
                id=case_name,
                marks=marks,
            )
        )

    return cases


GOLD_ROOT = Path(__file__).resolve().parents[2] / "agent" / "domain" / "evaluation" / "gold"
PATENT_CASES = discover_cases(GOLD_ROOT)


# ----------------------------------------------------------------------
# MAIN TEST
# ----------------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.llm
@pytest.mark.parametrize("case_name, url, gold_path, allow_extras", PATENT_CASES)
def test_llm_patent_coverage_all_gold(case_name, url, gold_path, allow_extras):
    # ======================== DEBUG GOLD ===============================
    expected_raw = _expected_patents(gold_path)

    print("\n====================== DEBUG GOLD ======================")
    print(f"[DEBUG] CASE_NAME          = {case_name}")
    print(f"[DEBUG] GOLD_PATH          = {gold_path}")
    print(f"[DEBUG] GOLD (NORMALIZED) = {sorted(expected_raw)}")
    print("========================================================\n")

    assert expected_raw, f"Gold {case_name} is empty or missing."

    # Build standard keys from expected
    expected_keys = {standard_pat_key(x) for x in expected_raw}
    expected_keys.discard(None)  # filter garbage

    # ==================== LLM EXTRACTION ===============================
    raw = asyncio.run(analyse_url(url, mode="patents"))
    assert raw, f"Empty extraction for {case_name} ({url})."

    parsed = parse_json_lines(raw)

    print("\n====================== DEBUG PARSED RAW =================")
    for entry in parsed:
        print(" RAW_ENTRY:", entry)
    print("========================================================\n")

    # ====================== PREDICTED ================================
    predicted_raw = {
        normalize_pat(
            entry.get("normalized_number")
            or entry.get("patent")
            or entry.get("patent_number")
            or entry.get("patentNumber")
            or entry.get("number_raw")
        )
        for entry in parsed
        if isinstance(entry, dict)
    }

    print("\n====================== DEBUG PREDICTED ==================")
    print("[DEBUG] PREDICTED (NORMALIZED) =", sorted(predicted_raw))
    print("========================================================\n")

    # Build standard keys from predicted
    predicted_keys = {standard_pat_key(x) for x in predicted_raw}
    predicted_keys.discard(None)  # filter garbage

    # ====================== COMPARISON ================================
    missing_keys = expected_keys - predicted_keys
    extra_keys = predicted_keys - expected_keys

    # Map back to original UCIDs for display
    missing = sorted([x for x in expected_raw if standard_pat_key(x) in missing_keys])
    extra = sorted([x for x in predicted_raw if standard_pat_key(x) in extra_keys])

    print(f"{case_name}: expected={len(expected_raw)} ; predicted={len(predicted_raw)}")
    if missing:
        print("MANQUANTS:", sorted(missing))
    if extra:
        print("INATTENDUS:", sorted(extra))

    # ======================= DEBUG KEY DETAILS ========================
    print("\n====================== DEBUG KEY DETAILS =================")

    if missing:
        print(">> MANQUANTS : clés manquantes")
        for e in sorted(missing):
            key = standard_pat_key(e)
            print(f"  {e} → standard={key}")

    if extra:
        print("\n>> INATTENDUS : clés inattendues")
        for p in sorted(extra):
            key = standard_pat_key(p)
            print(f"  {p} → standard={key}")

    print("========================================================\n")

    # ======================== ASSERTIONS ==============================
    assert not missing, f"Brevets manquants {case_name}: {sorted(missing)}"

    if not allow_extras:
        assert not extra, f"Brevets inattendus {case_name}: {sorted(extra)}"
