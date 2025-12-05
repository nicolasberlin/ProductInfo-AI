import argparse
import asyncio
import sys
from pathlib import Path

from agent.llm_inference.core import analyse_url


def _read_urls_from_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[WARN] Impossible de lire {path}: {exc}", file=sys.stderr)
        return []

    urls = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        urls.append(stripped)

    if not urls:
        print(f"[WARN] Fichier {path} vide, ignoré.", file=sys.stderr)
    return urls


def _expand_input(value: str) -> list[str]:
    """Transforme la valeur --input (URL, fichier .url, dossier) en liste de cibles."""
    value = (value or "").strip()
    if not value:
        return []

    lower = value.lower()
    if lower.startswith(("http://", "https://")):
        return [value]

    path = Path(value).expanduser()
    if path.is_file():
        if path.suffix.lower() == ".url":
            return _read_urls_from_file(path)
        # Traiter tout autre fichier comme un document à analyser (PDF local, etc.)
        return [str(path)]

    if path.is_dir():
        urls: list[str] = []
        for file in sorted(path.rglob("*.url")):
            urls.extend(_read_urls_from_file(file))
        if not urls:
            print(f"[WARN] Aucun fichier .url trouvé dans {path}", file=sys.stderr)
        return urls

    print(f"[WARN] Entrée inconnue ou introuvable: {value}. Utilisation brute.", file=sys.stderr)
    return [value]


def _collect_urls(positional: list[str], inputs: list[str]) -> list[str]:
    seen: set[str] = set()
    collected: list[str] = []
    for token in [*(positional or []), *(inputs or [])]:
        for url in _expand_input(token):
            if not url:
                continue
            if url not in seen:
                collected.append(url)
                seen.add(url)
    return collected


def main():
    parser = argparse.ArgumentParser(description="Analyse LLM (brevets, produits, mapping, audit OCR).")
    parser.add_argument(
        "url",
        nargs="*",
        help="URLs/chemins en argument positionnel (optionnel si --input est fourni).",
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="inputs",
        nargs="+",
        action="extend",
        default=[],
        help="URL directe, fichier .url ou dossier contenant des fichiers .url (répéter pour plusieurs valeurs).",
    )
    parser.add_argument("--mode", choices=["full", "audit", "patents", "products"], default="patents", help="Mode d’analyse.")
    args = parser.parse_args()

    targets = _collect_urls(args.url, args.inputs)
    if not targets:
        parser.error("Aucune URL fournie. Ajoute un argument positionnel ou un --input.")

    async def _run():
        if len(targets) == 1:
            res = await analyse_url(targets[0], mode=args.mode)
            if res:
                print(res)
        else:
            results = await asyncio.gather(*(analyse_url(u, mode=args.mode) for u in targets))
            for u, r in zip(targets, results):
                if r:
                    print(f"# URL: {u}")
                    print(r)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
