from openai import OpenAI
import sys
from agent.llm_prompts import (
    comparison_prompt,
    line_filter_prompt,
    mapping_products_patents_prompt,
    mapping_prompt,
    patent_token_json_extraction_prompt,
    product_name_extraction_prompt,
    product_name_from_document_prompt,
    span_to_pairs_prompt,
    span_trigger_prompt,
    validation_prompt,
)

client = OpenAI(api_key="REMOVED_OPENAI_KEYiMOkDuwssaR46hjXoFTuNinae_kEYAzPPYZWNMTx8asCIgHv02fl-V-fYGcO2McXFbymyG6vP3T3BlbkFJLsnaTo156STaU601nwtNPz8nH3S0fgDSOnhdmr7iVi6P8IysctI5PllKnjC-kHhwCqMOeP8C0A")  # Mets ta clé directement ici

def call_openai(message):
    response = client.responses.create(
        model="gpt-5-mini",
        input=message,
        max_output_tokens=10000,
        reasoning={"effort": "medium"},
        text={"verbosity": "low"},
    )
    return response.output_text or ""


def send_line_filter(document_text: str) -> str:
    try:
        messages = line_filter_prompt(document_text)
        print(f"[send_line_filter] messages: {messages}", file=sys.stderr)
        return call_openai(messages) or ""
    except Exception as e:
        print(f"[line_filter] error: {e}", file=sys.stderr)

def send_span_trigger(line_text: str) -> str:
    try:
        messages = span_trigger_prompt(line_text)
        #print(f"[send_span_trigger] messages: {messages}", file=sys.stderr)
        return call_openai(messages) or ""
    except Exception as e:
        print(f"[span_trigger] error: {e}", file=sys.stderr)

def send_span_to_pairs(span_objects_text: str) -> str:
    try:
        messages = span_to_pairs_prompt(span_objects_text)
        return call_openai(messages) or ""
    except Exception as e:
        print(f"[span_to_pairs] error: {e}", file=sys.stderr)

def send_mapping(document_text: str) -> str:
    try:
        messages = mapping_prompt(document_text)
        return call_openai(messages) or ""
    except Exception as e:
        print(f"[mapping] error: {e}", file=sys.stderr)

def send_comparison(document_text: str) -> str:
    try:
        messages = comparison_prompt(document_text)
        return call_openai(messages) or ""
    except Exception as e:
        print(f"[comparison] error: {e}", file=sys.stderr)

def send_validation(source_text: str, first_pass: str) -> str:
    try:
        messages = validation_prompt(source_text, first_pass)
        return call_openai(messages) or ""
    except Exception as e:
        print(f"[validation] error: {e}", file=sys.stderr)


def send_patent_token_json(document_text: str) -> str:
    messages = patent_token_json_extraction_prompt(document_text)
    return call_openai(messages) or ""

def send_product_names(document_text: str) -> str:
    messages = product_name_extraction_prompt(document_text)
    return call_openai(messages) or ""

def send_mapping_products_patents(product_list_jsonl: str, patent_list_jsonl: str, document_text: str) -> str:
    messages = mapping_products_patents_prompt(product_list_jsonl, patent_list_jsonl, document_text)
    return call_openai(messages) or ""



def send_product_name_from_document(document_text: str) -> str:
    messages = product_name_from_document_prompt(document_text)
    print(f"[send_product_name_from_document] messages: {messages}", file=sys.stderr)
    return call_openai(messages) or ""