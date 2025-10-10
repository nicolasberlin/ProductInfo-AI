import json, re, unicodedata
from collections import Counter
from typing import Iterable, Tuple, List, Set, Union

Pair = Tuple[str, str]  # (product, patent)

# ---------- Normalisation ----------
def normalize_prod(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower().strip()
    return re.sub(r"\s+", " ", s)

def normalize_pat(p: str) -> str:
    p = str(p).upper().replace(" ", "").strip()
    return p

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
            obj=json.loads(line)
            prods = obj.get("products") if "products" in obj else [obj.get("product","")]
            pats  = obj.get("patents")  if "patents"  in obj else [obj.get("patent","")]
            if isinstance(prods, str): prods=[prods]
            if isinstance(pats, str):  pats=[pats]
            for pr in prods:
                for pa in pats:
                    S.add((normalize_prod(pr), normalize_pat(pa)))
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
        prods = obj.get("products") if "products" in obj else [obj.get("product","")]
        pats  = obj.get("patents")  if "patents"  in obj else [obj.get("patent","")]
        if isinstance(prods, str): prods=[prods]
        if isinstance(pats, str):  pats=[pats]
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

