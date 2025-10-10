import json
import os, sys, time
from typing import Union, List

from agent.llm_calls import send_line_filter, send_mapping_products_patents, send_patent_token_json, send_product_name_from_document, send_product_names, send_span_to_pairs, send_span_trigger
from agent.llm_prompts import mapping_products_patents_prompt, patent_token_json_extraction_prompt, product_name_extraction_prompt
from agent.llm_utils import print_prompt
from agent.postprocressing.group_patents import extract_product_patent_pairs

DEFAULT_CHUNK_SIZE = 1000
RED = "\x1b[31m"; RESET = "\x1b[0m"

from agent.preprocess.context import normalize_text
from openai import OpenAI
from agent.preprocess.extractor import fetch_text, fetch_text_pages



def analyse_text(document_text: Union[str, List[str]]) -> str:
    """Analyse un texte entier (str) ou une liste de pages (List[str]).
    - str: conserve le flux conversationnel existant avec chat_history.
    - List[str]: appels stateless par page et fusion des lignes (déduplication).
    """
    RED = "\x1b[31m"; RESET = "\x1b[0m"

    #print(f"analyse_text: Document has {len(document_text) if isinstance(document_text, list) else len(document_text.split())} words", file=sys.stderr)

    # Cas 1: texte simple (compatibilité)
    if len(document_text) == 1 or isinstance(document_text, str):
        print("Cas 1: texte simple", file=sys.stderr)

        """
        #normalized_doc_text = normalize_text(document_text[0] if isinstance(document_text, list) else document_text)
        #print(f"{RED}Page 1 normalisée : {(normalized_doc_text)}){RESET}", file=sys.stderr)
        out = send_line_filter(document_text)
        """
        patents = send_patent_token_json(document_text)
        print(f"{RED}Page 1 normalisée : {(patents)}){RESET}", file=sys.stderr)


        products = send_product_names(document_text)
        print(f"{RED}Le out du deuxieme appel est :{RESET}\n{repr(products)}", file=sys.stderr)


        out = send_mapping_products_patents(products, patents, document_text)
        
        print(f"{RED}Le out du troisième appel est :{RESET}\n{repr(out)}", file=sys.stderr)

        """
        out = send_span_trigger(out)
        print(f"{RED}Le out du deuxieme appel est :{RESET}\n{repr(out)}", file=sys.stderr)
        """
        #out = extract_product_patent_pairs(out, dedup=False, strip_fields=True)
     
        # Second call: validation over the first-pass output
        #validated = _send_validation_message(out, document_text)
        #print(f"{RED}Le out du second appeldonn est :{RESET}\n{validated}", file=sys.stderr)
        # out = _send_comparison_message(out, document_text)
        # JSON pretty

        return out

    # Cas 2: liste de pages (stateless page-by-page)
    print("Cas 2: liste de pages", file=sys.stderr)
    outputs: list[str] = []
    seen: set[str] = set()
    for idx, page_text in enumerate(document_text, start=1):
        if not (page_text or "").strip():
            continue
        
        print(f"{RED}Premier appel:  : {(page_text)}){RESET}", file=sys.stderr)
        patents = send_patent_token_json(page_text)
        print(f"{RED}Premier appel:  : {(patents)}){RESET}", file=sys.stderr)

        products = send_product_names(page_text)
        print(f"{RED}Le out du deuxieme appel est :{RESET}\n{repr(products)}", file=sys.stderr)

        """
        out = send_mapping_products_patents(products, patents, page_text)
        
        print(f"{RED}Le out du troisième appel est :{RESET}\n{repr(out)}", file=sys.stderr)
        """
        
        """
        out = send_product_name_from_document(page_text)
        print(f"{RED}Le out du  appel est :{RESET}\n{repr(out)}", file=sys.stderr)
        """

        validated_chunk = out
       
        #print(f"{RED}Le out du 3eme appel est :{RESET}\n{validated_chunk}", file=sys.stderr)
        #validated_chunk = group_patents_by_product(validated_chunk)

        for line in validated_chunk.splitlines():
            line = line.strip()
            if line and line not in seen:
                seen.add(line)
                outputs.append(line)
    # Join de-duplicated lines then run validation once
    #print(f"[DEBUG] analyse_text returns:\n{repr(outputs)}", file=sys.stderr)

    out = send_mapping_products_patents(products, patents, page_text)
        
    print(f"{RED}Le out du troisième appel est :{RESET}\n{repr(out)}", file=sys.stderr)


    joined = "\n".join(outputs)
    #print(f"Output du 1eme appel \n {repr(joined)}", file=sys.stderr)

    #print(f"Output du 2eme appel \n{joined}", file=sys.stderr)
    #print(f"[DEBUG] analyse_text returns (joined):\n{repr(joined)}", file=sys.stderr)
    #return "\n".join(outputs)
    return joined

def analyse_url(url: str) -> str:
    """
    Récupère le contenu (HTML ou PDF). Pour PDF, traite page par page.
    """
    #print(f"analyse_url: Fetching document from {url}", file=sys.stderr)

    pages = fetch_text_pages(url)
    #print(f"analyse_url: pages {(pages)}", file=sys.stderr)
    #print(f"[infer] Sending document to OpenAI (page-aware)", file=sys.stderr)
    result = analyse_text(pages)
    print(f"[DEBUG] Type de result : {type(result)}", file=sys.stderr)
    if isinstance(result, str):
        print(f"[DEBUG] Aperçu result (str, 500 premiers caractères) :\n{result[:500]}", file=sys.stderr)
    elif isinstance(result, list):
        print(f"[DEBUG] Aperçu result (list, premiers éléments) : {result[:6]}", file=sys.stderr)
    else:
        print(f"[DEBUG] Aperçu result (repr) : {repr(result)}", file=sys.stderr)

    #out = regrouper_brevets_par_produit(result)
    #patents_text = group_patents_by_product(result)
    #print(f"[infer] ✅ Document processed", file=sys.stderr)
    #print(f"[infer] Result:\n{result}", file=sys.stderr)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agent.infer_gpt <url> [--show-prompt] [--show-text] [--print-chunks] [--chunk-size N]")
        sys.exit(1)
    if "--chunk-size" in sys.argv:
        idx = sys.argv.index("--chunk-size")
        if idx + 1 < len(sys.argv):
            try:
                DEFAULT_CHUNK_SIZE = int(sys.argv[idx + 1])
            except ValueError:
                pass
    url = sys.argv[1]
    if "--show-prompt" in sys.argv:
        print_prompt(url)
    elif "--show-text" in sys.argv:
        print(repr(fetch_text(url)))
    else:
        print(analyse_url(url))
