import argparse
import asyncio
from pathlib import Path

from agent.llm_inference.llm_inference import analyse_url, analyse_many_urls
from agent.evaluation.utils import (
    compare_in_memory,
    load_gold_pairs,
    pairs_from_result,
)

GOLD_ROOT = Path("agent/evaluation/gold")
DEFAULT_REPORT_DIR = Path("agent/evaluation/reports")


def find_gold_for_url(url: str) -> Path | None:
    """Scan all gold files and return the one whose first line equals the URL."""
    for path in GOLD_ROOT.rglob("*.ndjson"):
        try:
            with path.open("r", encoding="utf-8") as f:
                first = f.readline().strip()
        except OSError:
            continue
        if first.startswith('"') and first.endswith('"'):
            first = first[1:-1]
        if first == url:
            return path
    return None


def main():
    parser = argparse.ArgumentParser(description="Compare LLM extraction to gold annotations for a given URL.")
    parser.add_argument("url", nargs="+", help="One or more document URLs to analyse.")
    parser.add_argument(
        "--gold",
        help="Optional path to the gold NDJSON file. If omitted we pick the file whose first line matches the URL.",
    )
    parser.add_argument(
        "--report",
        help="Optional TSV output path (defaults to agent/evaluation/reports/<slug>.tsv).",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=4,
        help="Maximum number of concurrent LLM analyses (only relevant when passing multiple URLs).",
    )
    args = parser.parse_args()

    DEFAULT_REPORT_DIR.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[str, Path]] = []
    fixed_gold = Path(args.gold) if args.gold else None

    for url in args.url:
        gold_path = fixed_gold if fixed_gold else find_gold_for_url(url)
        if not gold_path:
            print(f"[WARN] Aucun gold trouvé pour {url}. Ignoré.")
            continue
        if not gold_path.is_file():
            print(f"[WARN] Gold introuvable: {gold_path}. Ignoré.")
            continue
        targets.append((url, gold_path))

    if not targets:
        print("Aucun URL valide à traiter.")
        return

    urls = [url for url, _ in targets]

    if len(urls) == 1:
        print(f"Analyse LLM de {urls[0]} ...")
        result_output = asyncio.run(analyse_url(urls[0]))
        results = {urls[0]: {"ok": True, "output": result_output}}
    else:
        print(f"Analyse de {len(urls)} URLs (max_concurrency={args.max_concurrency}) ...")
        raw_results = asyncio.run(analyse_many_urls(urls, max_concurrency=args.max_concurrency))
        results = {r["url"]: r for r in raw_results}

    for url, gold_path in targets:
        res = results.get(url)
        if not res:
            print(f"[WARN] Aucun résultat pour {url}. Ignoré.")
            continue
        if not res.get("ok"):
            err = res.get("error")
            if err is None:
                print(f"[ERROR] Analyse LLM échouée pour {url}: erreur inconnue (vérifie la clé API ou la connectivité réseau).")
            else:
                print(f"[ERROR] Analyse LLM échouée pour {url}: {err!r}")
            continue

        result = res["output"]

        report_path = Path(args.report) if args.report else DEFAULT_REPORT_DIR / (gold_path.stem + "_compare.tsv")

        gold_pairs = sorted(load_gold_pairs(str(gold_path)))
        pred_pairs = sorted(pairs_from_result(result))

        stats = compare_in_memory(
            result_llm=result,
            gold_path=str(gold_path),
            report_tsv=str(report_path),
        )
        print(f"Gold pairs (normalisés) : {gold_pairs}")
        print(f"Paires LLM (normalisées) : {pred_pairs}")
        print("Métriques :")
        metric_order = [
            "gold", "pred", "tp", "fp", "fn",
            "precision", "recall", "f1",
            "top_missing", "top_spurious",
            "tp_examples", "fp_examples", "fn_examples",
        ]
        for key in metric_order:
            if key in stats:
                print(f"  {key}: {stats[key]}")
        print(f"Rapport TSV : {report_path}")
        print("")


if __name__ == "__main__":
    main()
