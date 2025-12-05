import asyncio
import json
from pathlib import Path
import sys
import pytest
from rapidfuzz import fuzz

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Core LLM dispatcher
from agent.llm_inference.core import analyse_url  # noqa: E402

# JSON-lines parser (compatibility shim if path changed)
try:
    from agent.llm.llm_utils import parse_json_lines  # noqa: E402
except ImportError:  # pragma: no cover
    from agent.llm_utils import parse_json_lines  # type: ignore  # noqa: E402

from agent.evaluation.normalization import normalize_prod  # noqa: E402


# Clés possibles contenant un nom de produit dans la sortie LLM.
# Le LLM n'est pas strict, donc on accepte plusieurs variantes.
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
    Extrait tous les champs qui pourraient contenir un nom de produit
    depuis un dict retourné par le LLM.

    Exemple :
      {"product_name": "Tile Mount", "confidence": 0.9}
      -> ["Tile Mount"]

      {"product": ["Hook A", "Hook B"]}
      -> ["Hook A", "Hook B"]
    """
    values = []
    for key in PRODUCT_KEYS:
        if key in obj and obj[key]:
            val = obj[key]

            # Si la valeur est une liste → extraire chaque élément
            if isinstance(val, (list, tuple, set)):
                values.extend(str(v) for v in val if v)

            # Sinon extraire la valeur unique
            else:
                values.append(str(val))
    return values


def _allow_extras_from_path(path: Path, base_dir: Path) -> bool:
    """Retourne False pour tout fichier situé sous un dossier 'columns'."""
    rel_parts = path.relative_to(base_dir).parts
    return "columns" not in rel_parts


def discover_product_cases(base_dir: Path) -> list[tuple[str, str, Path, bool]]:
    """
    Parcourt agent/evaluation/gold/ (récursif) pour trouver automatiquement :
    - les fichiers .ndjson (produits attendus)
    - les fichiers .url associés (URL à analyser)
    - le mode allow_extras selon l'appartenance à 'columns'

    Cela permet d'ajouter des cas de test sans toucher le code.
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


# Prépare la liste de cas de test paramétrés pour pytest
GOLD_ROOT = PROJECT_ROOT / "agent" / "evaluation" / "gold"
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
    Charge les produits 'gold' (vérité terrain) depuis un fichier .ndjson.
    Normalise chaque produit → permet une comparaison fiable.

    On ignore les lignes vides, commentaires, ou JSON non dict.
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
    Test fuzzy : True si item est similaire à un élément du set.
    Tolère les petites variations d'écriture du LLM.
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
    Test principal :
      1. Charge les produits gold
      2. Appelle l'agent LLM sur l'URL
      3. Extrait + normalise les produits prédits
      4. Compare gold vs LLM (fuzzy)
      5. Échec si produits manquants ou inattendus (selon les règles)
    """

    # 1. Produits attendus depuis le gold
    expected = _expected_product_set_from_gold(gold_path)
    assert expected, f"Gold {case_name} vide ou introuvable ({gold_path})."

    # 2. Appel du LLM
    raw = asyncio.run(analyse_url(url, mode="products"))
    assert raw, f"Extraction vide pour {case_name} ({url})."

    # Conversion JSON-lines → liste de dicts
    parsed = parse_json_lines(raw)
    print(f"[llm products raw] {parsed}")

    # 3. Extraction + normalisation des produits prédits
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

    # 4. Comparaison fuzzy
    missing = {e for e in expected if not fuzzy_in(e, predicted)}
    extra   = {p for p in predicted if not fuzzy_in(p, expected)}

    print(f"{case_name} produits: attendus={len(expected)} prédits={len(predicted)}")
    if missing:
        print("Manquants:", sorted(missing))
    if extra:
        print("Inattendus:", sorted(extra))

    # Aide au diagnostic : montre les produits avec similarité faible
    for e in expected:
        scores = [(fuzz.ratio(e, p), p) for p in predicted]
        if not scores:
            continue
        best = max(scores)
        if best[0] < 90:
            print(f"[WARN] Similarité faible {best[0]:.1f}% pour produit '{e}' vs '{best[1]}'")

    # 5. Critères d'échec
    assert not missing, f"Produits manquants {case_name}: {sorted(missing)}"
    if not allow_extras:
        assert not extra, f"Produits inattendus {case_name}: {sorted(extra)}"
