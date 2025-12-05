import sys
import json
import re

# Import relatif (même dossier) pour exécution directe: python api/normalize_patents.py
from get_ucid import select_best_ucid

# Ex: "US9439375B2" ou "US9949455"
PATENT_RE = re.compile(r"^([A-Z]{2})(\d+)([A-Z]\d)?$")

def normalize_patent(raw_patent: str) -> str:
    """
    Prend une chaîne comme 'US9949455' ou 'US9439375B2'
    -> retourne l'UCID normalisé (ex: 'US9949455B2') si possible,
       sinon renvoie la chaîne d'origine.
    """
    raw = raw_patent.upper().replace(" ", "").strip()

    raw = re.sub(r"\([^)]*\)", "", raw)

    m = PATENT_RE.match(raw)
    if not m:
        # format bizarre -> on ne touche pas
        return raw

    country, num, _kind = m.group(1), m.group(2), m.group(3)

    # Appel à ton API Google Patents
    candidate = f"{country}{num}"

    ucid = select_best_ucid(num, country)

  


    return ucid if ucid else raw

def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        obj = json.loads(line)

        patent_raw = obj.get("patent", "")
        if patent_raw:
            obj["patent"] = normalize_patent(patent_raw)
            # Affiche le mapping pour inspection (stderr pour ne pas polluer la sortie NDJSON)
            try:
                print(f"[normalize] raw='{patent_raw}' -> '{obj['patent']}'", file=sys.stderr)
            except Exception:
                pass

        # On réimprime une ligne JSON propre
        print(json.dumps(obj, ensure_ascii=False))

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
