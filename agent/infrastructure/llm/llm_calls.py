import os
from openai import AsyncOpenAI
from agent.domain.prompts.llm_prompts import (
    mapping_products_patents_prompt,
    patent_token_json_extraction_prompt,
    product_name_extraction_prompt,
    product_name_from_document_prompt,
    group_mappings_by_product_prompt,
    products_patents_audit_prompt,
)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("Missing OPENAI_API_KEY (export OPENAI_API_KEY=... before running)")
client = AsyncOpenAI(api_key=api_key)

async def call_openai(message):
    # message: prompt string
    resp = await client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        input=message,
        max_output_tokens=10000,
        reasoning={"effort": "medium"},
        text={"verbosity": "low"},
    )
    return resp.output_text or ""

async def send_patent_token_json(document_text: str) -> str:
    prompt = patent_token_json_extraction_prompt(document_text or "")
    return await call_openai(prompt) or ""

async def send_product_names(document_text: str) -> str:
    prompt = product_name_extraction_prompt(document_text or "")
    return await call_openai(prompt) or ""

async def send_mapping_products_patents(product_list_jsonl: str, patent_list_jsonl: str, document_text: str) -> str:
    prompt = mapping_products_patents_prompt(product_list_jsonl or "", patent_list_jsonl or "", document_text or "")
    return await call_openai(prompt) or ""

async def send_group_mappings_by_product(mapping_jsonl: str) -> str:
    prompt = group_mappings_by_product_prompt(mapping_jsonl or "")
    return await call_openai(prompt) or ""

async def send_product_name_from_document(document_text: str) -> str:
    prompt = product_name_from_document_prompt(document_text or "")
    return await call_openai(prompt) or ""

async def send_verification_audit(products: str, patents: str, document_text: str) -> str:
    prompt = products_patents_audit_prompt(products or "", patents or "", document_text or "")
    return await call_openai(prompt) or ""

__all__ = [
    "send_patent_token_json",
    "send_product_names",
    "send_mapping_products_patents",
    "send_group_mappings_by_product",
    "call_openai",
    "send_verification_audit",
    "send_product_name_from_document",
]
