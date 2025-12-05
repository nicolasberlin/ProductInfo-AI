import json
from collections import Counter
from typing import Iterable, Tuple, List, Set, Union

Pair = Tuple[str, str]  # (product, patent)

from agent.evaluation.normalization import normalize_prod, normalize_pat

# ---------- Lecture du GOLD ----------
def load_gold_pairs(path: str) -> Set[Pair]:
    S: Set[Pair] = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(("//", "#", "/*", "*", "*/")):
                continue
            try:
                obj=json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            # Accept both singular/plural keys and list or string values
            prods_val = obj.get("products") if "products" in obj else obj.get("product", [])
            pats_val  = obj.get("patents")  if "patents"  in obj else obj.get("patent", [])

            prods = prods_val if isinstance(prods_val, list) else [prods_val]
            pats  = pats_val  if isinstance(pats_val, list)  else [pats_val]

            for pr in prods:
                for pa in pats:
                    if pr and pa:
                        # normalize_pat historically accepted dicts; ensure we pass a dict
                        pa_obj = pa if isinstance(pa, dict) else {"number_raw": pa}
                        S.add((normalize_prod(pr), normalize_pat(pa_obj)))
    return S

# ---------- Parsing de la sortie LLM EN MÉMOIRE ----------
def pairs_from_result(result: Union[str, list]) -> Set[Pair]:
    """
    Accepte:
      - str NDJSON (une ligne = objet)
      - str JSON (liste d'objets)
      - list[dict] déjà parsée
    Retourne set de (product, patent)
    """
    items: List[dict] = []
    if isinstance(result, list):
        items = result
    elif isinstance(result, str):
        txt = result.strip()
        if txt.startswith("["):            # JSON array
            items = json.loads(txt)
        else:                               # NDJSON
            for ln in txt.splitlines():
                ln = ln.strip()
                if not ln: 
                    continue
                try:
                    items.append(json.loads(ln))
                except json.JSONDecodeError:
                    # ignorer lignes non-JSON éventuelles
                    continue
    else:
        raise TypeError("Résultat LLM non supporté")

    S: Set[Pair] = set()
    for obj in items:
        if not isinstance(obj, dict): 
            continue
        def pick(obj, keys, default=None):
            for key in keys:
                if key in obj and obj[key] not in (None, ""):
                    return obj[key]
            return default

        prods_raw = pick(obj, ("products", "product", "product_name", "productName"), [])
        pats_raw = pick(obj, ("patents", "patent", "patent_number", "patentNumber"), [])

        prods = prods_raw if isinstance(prods_raw, list) else [prods_raw]
        pats = pats_raw if isinstance(pats_raw, list) else [pats_raw]

        for pr in prods:
            for pa in pats:
                if pr and pa:
                    S.add((normalize_prod(pr), normalize_pat(pa)))
    return S

# ---------- Métriques ----------
def prf(tp, fp, fn):
    prec = tp/(tp+fp) if tp+fp>0 else 0.0
    rec  = tp/(tp+fn) if tp+fn>0 else 0.0
    f1   = 2*prec*rec/(prec+rec) if prec+rec>0 else 0.0
    return prec, rec, f1

def compare_in_memory(result_llm: Union[str, list], gold_path: str, report_tsv: str|None=None):
    G = load_gold_pairs(gold_path)
    P = pairs_from_result(result_llm)

    tp = G & P
    fp = P - G
    fn = G - P

    prec, rec, f1 = prf(len(tp), len(fp), len(fn))

    if report_tsv:
        with open(report_tsv, "w", encoding="utf-8") as out:
            out.write("type\tproduct\tpatent\n")
            for p,a in sorted(tp): out.write(f"TP\t{p}\t{a}\n")
            for p,a in sorted(fp): out.write(f"FP\t{p}\t{a}\n")
            for p,a in sorted(fn): out.write(f"FN\t{p}\t{a}\n")

    return {
        "gold": len(G), "pred": len(P),
        "tp": len(tp), "fp": len(fp), "fn": len(fn),
        "precision": prec, "recall": rec, "f1": f1,
        "top_missing": Counter(p for p,_ in fn).most_common(5),
        "top_spurious": Counter(p for p,_ in fp).most_common(5),
        "tp_examples": list(sorted(tp))[:5],
        "fp_examples": list(sorted(fp))[:5],
        "fn_examples": list(sorted(fn))[:5],
    }
