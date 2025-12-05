import asyncio
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from rapidfuzz import fuzz

from agent.evaluation.normalization import normalize_pat
from agent.llm.llm_utils import parse_json_lines
from agent.llm_inference.core import analyse_url



def _allow_extras_from_path(path: Path, base_dir: Path) -> bool:
    """Retourne False pour tout fichier situé sous un dossier 'columns'."""
    rel_parts = path.relative_to(base_dir).parts
    return "columns" not in rel_parts


def discover_patent_cases(base_dir: Path) -> list[tuple[str, str, Path, bool]]:
    """Découvre automatiquement les cas de test depuis la hiérarchie gold/ (récursif)."""
    cases = []
    for ndjson_path in base_dir.rglob("*.ndjson"):
        allow_extras = _allow_extras_from_path(ndjson_path, base_dir)
        case_name = ndjson_path.stem
        url_file = ndjson_path.with_suffix(".url")
        if not url_file.exists():
            print(f"[WARN] Aucun .url trouvé pour {ndjson_path.name}, ignoré.")
            continue
        url = url_file.read_text().strip()
        if not url:
            print(f"[WARN] Fichier .url vide pour {case_name}, ignoré.")
            continue
        cases.append((case_name, url, ndjson_path, allow_extras))
    return cases


GOLD_ROOT = PROJECT_ROOT / "agent" / "evaluation" / "gold"
PATENT_CASES: list = []
for name, url, gold_path, allow_extras in discover_patent_cases(GOLD_ROOT):
    marks = []
    if not allow_extras:
        marks.append(pytest.mark.columns)
    PATENT_CASES.append(
        pytest.param(name, url, gold_path, allow_extras, id=name, marks=marks)
    )


def _expected_patent_set_from_gold(path: Path) -> set[str]:
    expected = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            pat = obj.get("patent") or obj.get("patent_number")
            if pat:
                expected.add(normalize_pat(pat))
    return expected


def fuzzy_in(item: str, candidates: set[str], threshold: int = 90) -> bool:
    """Retourne True si `item` est proche d'au moins un élément de `candidates`."""
    for cand in candidates:
        if fuzz.ratio(item, cand) >= threshold:
            return True
    return False

from rapidfuzz import fuzz

def top_matches(x, candidates, k=5):
    scores = [(c, fuzz.ratio(x, c)) for c in candidates]
    scores.sort(key=lambda t: t[1], reverse=True)
    return scores[:k]


@pytest.mark.slow
@pytest.mark.llm
@pytest.mark.parametrize("case_name, url, gold_path, allow_extras", PATENT_CASES)
def test_llm_patent_coverage_all_gold(case_name: str, url: str, gold_path: Path, allow_extras: bool):
    # ----------------------------------------------------------------------
    # DEBUG 1 : Inspecter ce que contient le GOLD (vérité de référence)
    # ----------------------------------------------------------------------
    expected = _expected_patent_set_from_gold(gold_path)

    print("\n====================== DEBUG GOLD ======================")
    print(f"[DEBUG] CASE_NAME   = {case_name}")
    print(f"[DEBUG] GOLD_PATH   = {gold_path}")
    print(f"[DEBUG] EXPECTED (NORMALIZED) = {sorted(expected)}")
    print("========================================================\n")

    assert expected, f"Gold {case_name} vide ou introuvable ({gold_path})."

    # ----------------------------------------------------------------------
    # LLM extraction
    # ----------------------------------------------------------------------
    raw = asyncio.run(analyse_url(url, mode="patents"))
    assert raw, f"Extraction vide pour {case_name} ({url})."
    parsed = parse_json_lines(raw)

    print("\n====================== DEBUG PARSED RAW =================")
    for entry in parsed:
        print(" RAW_ENTRY:", entry)
    print("========================================================\n")

    # ----------------------------------------------------------------------
    # DEBUG 2 : Normalisation des brevets prédits
    # ----------------------------------------------------------------------
    predicted = {
        normalize_pat(
            entry.get("normalized_number")
            or entry.get("patent")
            or entry.get("patent_number")
            or entry.get("patentNumber")
            or entry.get("number_raw")
        )
        for entry in parsed
        if isinstance(entry, dict)
        and any(
            entry.get(k)
            for k in (
                "normalized_number",
                "patent",
                "patent_number",
                "patentNumber",
                "number_raw",
            )
        )
    }

    print("\n====================== DEBUG PREDICTED ==================")
    print("[DEBUG] PREDICTED (NORMALIZED) =", sorted(predicted))
    print("========================================================\n")

    # ----------------------------------------------------------------------
    # Comparaison fuzzy
    # ----------------------------------------------------------------------
    missing = {e for e in expected if not fuzzy_in(e, predicted)}
    extra = {p for p in predicted if not fuzzy_in(p, expected)}

    print(f"{case_name}: attendus={len(expected)} ; prédits={len(predicted)}")
    if missing:
        print("MANQUANTS:", sorted(missing))
    if extra:
        print("INATTENDUS:", sorted(extra))

    # ----------------------------------------------------------------------
    # DEBUG 3 : Scores fuzzy détaillés
    # ----------------------------------------------------------------------
    print("\n====================== DEBUG FUZZY DETAILS ===============")

    # 1) Détails pour les manquants
    if missing:
        print(">> MANQUANTS : meilleurs matches dans PREDICTED")
        for e in sorted(missing):
            best = top_matches(e, predicted, k=5)
            print(f"\n[expected manquant] {e}")
            for p, s in best:
                print(f"  predicted={p:<15}  score={s}")

    # 2) Détails pour les inattendus
    if extra:
        print("\n>> INATTENDUS : meilleurs matches dans EXPECTED")
        for p in sorted(extra):
            best = top_matches(p, expected, k=5)
            print(f"\n[predicted inattendu] {p}")
            for e, s in best:
                print(f"  expected={e:<15}  score={s}")

    print("========================================================\n")

    # ----------------------------------------------------------------------
    # Assertions finales
    # ----------------------------------------------------------------------
    assert not missing, f"Brevets manquants {case_name}: {sorted(missing)}"
    if not allow_extras:
        assert not extra, f"Brevets inattendus {case_name}: {sorted(extra)}"
