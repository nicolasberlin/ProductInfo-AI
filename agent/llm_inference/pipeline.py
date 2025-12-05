import asyncio
import json
import sys
from typing import Union, List

from agent.llm_calls import (
    send_patent_token_json,
    send_product_names,
    send_mapping_products_patents,
    send_group_mappings_by_product,
    send_verification_audit,
)
from agent.llm_utils import parse_json_lines, normalize_pages


def log(msg: str):
    print(msg, file=sys.stderr, flush=True)


def to_jsonl(items: list[dict]) -> str:
    """Convertit une liste de dicts en NDJSON."""
    return "\n".join(json.dumps(x, ensure_ascii=False) for x in items if x)


async def safe_call(coro, name: str):
    """Exécute une coroutine sans casser le pipeline si erreur."""
    try:
        return await coro
    except Exception as e:
        log(f"[ERROR] {name}: {e}")
        return ""



