import argparse
import asyncio
import os
import sys
from pathlib import Path

from agent.application.llm_inference.core import analyse_url
from agent.application.llm_inference.essential import (
    essentials_from_raw,
    filename_from_url,
    resolve_patents_with_api,
    write_essential,
)


def _read_urls_from_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[WARN] Unable to read {path}: {exc}", file=sys.stderr)
        return []

    urls = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        urls.append(stripped)

    if not urls:
        print(f"[WARN] File {path} is empty, ignored.", file=sys.stderr)
    return urls


def _expand_input(value: str) -> list[str]:
    """Expand --input (URL, .url file, directory) into a list of targets."""
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
        # Treat any other file as a document to analyse (local PDF, etc.)
        return [str(path)]

    if path.is_dir():
        urls: list[str] = []
        for file in sorted(path.rglob("*.url")):
            urls.extend(_read_urls_from_file(file))
        if not urls:
            print(f"[WARN] No .url file found in {path}", file=sys.stderr)
        return urls

    print(f"[WARN] Unknown or missing input: {value}. Using raw value.", file=sys.stderr)
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
    parser = argparse.ArgumentParser(description="LLM analysis (patents, products, mapping, OCR audit).")
    parser.add_argument(
        "url",
        nargs="*",
        help="URLs/paths as positional args (optional if --input is provided).",
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="inputs",
        nargs="+",
        action="extend",
        default=[],
        help="Direct URL, .url file, or folder containing .url files (repeatable).",
    )
    parser.add_argument("--mode", choices=["full", "audit", "patents", "products"], default="patents", help="Analysis mode.")
    parser.add_argument("--ocr", choices=["on", "off"], default=None, help="Force OCR usage for this run (on/off).")
    parser.add_argument(
        "--write-essential",
        action="store_true",
        help="Write an essential NDJSON (products/patents) into agent/reports/essential.",
    )
    args = parser.parse_args()

    # Override global OCR usage if explicitly specified
    if args.ocr == "on":
        os.environ["USE_OCR"] = "1"
    elif args.ocr == "off":
        os.environ["USE_OCR"] = "0"

    targets = _collect_urls(args.url, args.inputs)
    if not targets:
        parser.error("No URL provided. Add a positional argument or an --input.")

    # Log URL dans les messages START seulement en cas de batch
    os.environ["LOG_URL_START"] = "1" if len(targets) > 1 else "0"

    async def _run():
        if len(targets) == 1:
            res = await analyse_url(targets[0], mode=args.mode)
            if res:
                print(res)
                if args.write_essential:
                    products, patents = essentials_from_raw(res, args.mode)
                    patents = resolve_patents_with_api(patents)
                    out_dir = Path("agent") / "reports"
                    out_path = out_dir / filename_from_url(targets[0], ext=".essential.ndjson")
                    write_essential(out_path, targets[0], products, patents)
                    print(f"[ESSENTIAL] Écrit {out_path}", file=sys.stderr, flush=True)
        else:
            results = await asyncio.gather(*(analyse_url(u, mode=args.mode) for u in targets))
            for u, r in zip(targets, results):
                if r:
                    print(f"# URL: {u}")
                    print(r)
                    if args.write_essential:
                        products, patents = essentials_from_raw(r, args.mode)
                        patents = resolve_patents_with_api(patents)
                        out_dir = Path("agent") / "reports"
                        out_path = out_dir / filename_from_url(u, ext=".essential.ndjson")
                        write_essential(out_path, u, products, patents)
                        print(f"[ESSENTIAL] Écrit {out_path}", file=sys.stderr, flush=True)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
