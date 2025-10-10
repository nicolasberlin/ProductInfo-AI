import json
from json import JSONDecoder
from typing import List, Dict, Iterable, Tuple, Any

def extract_product_patent_pairs(raw: str, dedup: bool = False, strip_fields: bool = False) -> List[Dict[str, str]]:
    """
    Transforme une sortie LLM brute (texte avec objets JSON enchaînés, NDJSON ou liste)
    en liste de paires {"product": ..., "patent": ...} via produit cartésien Products × Patents.
    - dedup=True supprime les doublons exacts.
    - strip_fields=True applique .strip() sur product et patent.
    """
    def _normalize(s: str) -> str:
        s = s.strip()
        lower = s.lower()
        if lower.startswith("le output :") or lower.startswith("le output:"):
            s = s.split(":", 1)[1].strip()
        # retire guillemets englobants
        if (len(s) >= 2) and ((s[0] == s[-1]) and s[0] in ("'", '"')):
            s = s[1:-1]
        # transforme les "\n" littéraux en vrais retours
        s = s.replace("\\n", "\n")
        return s

    def _iter_json_objects(s: str) -> Iterable[Any]:
        dec = JSONDecoder()
        i, n = 0, len(s)
        while i < n:
            # sauter espaces
            while i < n and s[i].isspace():
                i += 1
            if i >= n:
                break
            try:
                obj, end = dec.raw_decode(s, i)
                if isinstance(obj, list):
                    for x in obj:
                        yield x
                else:
                    yield obj
                i = end
            except json.JSONDecodeError:
                # chercher le prochain '{' plausible
                j = s.find("{", i + 1)
                if j < 0:
                    break
                i = j

    s = _normalize(raw)
    out: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()

    for obj in _iter_json_objects(s):
        if not isinstance(obj, dict):
            continue
        products = obj.get("products")
        patents = obj.get("patents")
        # coercition légère
        if isinstance(products, str):
            products = [products]
        if isinstance(patents, str):
            patents = [patents]
        if not isinstance(products, list) or not isinstance(patents, list):
            continue

        for p in products:
            for b in patents:
                if not isinstance(p, str) or not isinstance(b, str):
                    continue
                pp = p.strip() if strip_fields else p
                bb = b.strip() if strip_fields else b
                key = (pp, bb)
                if dedup and key in seen:
                    continue
                if dedup:
                    seen.add(key)
                out.append({"product": pp, "patent": bb})
    return out

