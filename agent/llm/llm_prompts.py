PATENT_TOKEN_JSON_EXTRACTION = """

SYSTEM
You extract patent-like tokens from messy text (OCR noise, tables, lists).
Output only JSON Lines, one object per detected token. Do not emit prose or blank lines.

TASK
Detect all patent or patent-application numbers in the input text.
For each detected token, output one JSON object with these keys:
- "number_raw": token exactly as it appears (keep punctuation, spaces)
- "country": 2-letter WIPO code (US, EP, CN, etc.); leave empty string if you cannot infer it
- "kind": "design" if it starts with "D" and looks like a U.S. design patent (e.g. D847658 or USD847658), "utility" for standard patent/publication formats (e.g. WO2012/04545, US 2023/0187654), otherwise "unknown"
- "confidence": float in [0.0, 1.0] with up to three decimals; decrease below 0.7 when unsure
- "normalized_number": uppercase patent identifier prefixed with the WIPO code (if known) and stripped of spaces/punctuation (e.g. US10507399). Use empty string if normalization fails.

RULES
- Match any plausible patent identifier (examples: US10507399, WO2012/04545, ZL201180013089.X, Canada 2,688,262).
- Ignore phone numbers, dates, and prices.
- Preserve text exactly for "number_raw".
- Remove duplicates.
- Keep "number_raw" unchanged even when you infer a country code. Apply inferred codes only to "country" and "normalized_number".
- The patent must be associated with a WIPO country code (e.g., US, EP, CN). If missing but inferable from context (e.g., "United States Patent No. 9,754,465"), set "country" to the inferred code and prefix "normalized_number" with it.
- If you cannot infer any country code, keep both "country" and "normalized_number" as empty strings rather than guessing.
- Local code normalization:
  - Convert ZL → CN (China)
  - Convert E → ES (Spain)
  - Convert UK → GB (United Kingdom)
  - Keep all letters uppercase. Remove spaces, commas, periods, hyphens, parentheses.
- When stripping punctuation, retain trailing letters that are part of the identifier (e.g. ZL201180013089.X → CN201180013089X).
- Normalized format: always COUNTRYCODE + NUMBER without punctuation (e.g., CN2015800437105, ES10795846, US9473066).
- Each "normalized_number" must represent exactly one identifier and match a single-country pattern (e.g., starts with one country code followed by digits/letters). If a token appears merged, segment by known patterns (country code boundaries, digit length, punctuation in number_raw).
- For each patent, assign country origin based on the text : look first for a close mention of the country name or code near the patent number. If none, use the most likely country based on the text.

 
WIPO COUNTRY CODES :
    Use these mappings when inferring the 2-letter code for the "country" field:
    Canada → CA
    China → CN
    European Patent Convention / Europe → EP
    France → FR
    Germany → DE
    Italy → IT
    Japan → JP
    Russia → RU
    Spain → ES
    United Kingdom → GB
    United States → US


EXAMPLE INPUT
Trima™ systems
United States 10507399, Canada 2,688,262, JP 6031234, EP 2435612

EXPECTED OUTPUT
{"number_raw": "United States 10507399", "country": "US", "kind": "utility", "confidence": 1.0, "normalized_number": "US10507399"}
{"number_raw": "Canada 2,688,262", "country": "CA", "kind": "utility", "confidence": 1.0, "normalized_number": "CA2688262"}
{"number_raw": "JP 6031234", "country": "JP", "kind": "utility", "confidence": 1.0, "normalized_number": "JP6031234"}
{"number_raw": "EP 2435612", "country": "EP", "kind": "utility", "confidence": 1.0, "normalized_number": "EP2435612"}
"""



PRODUCT_NAME_EXTRACTION = """
SYSTEM
You are an information extractor. Your task is to find all distinct product names mentioned in the text.
Output JSON Lines only.

TASK
From the input text, detect every product name and output EXACTLY one JSON object per line with:
- "product_name": the product name exactly as written 
- "confidence": float ∈ [0,1] estimating certainty

RULES
1. A product name is a commercial or branded item (goods, software, medical device, chemical reagent, etc.) — not a company, patent, or person.
2. Keep full names with their brand qualifiers, version, and descriptors (e.g., “Elmer’s Magical Liquid”, “TACSI™ Disposable Cartridge”, “MEXA-7000”, “Trima Accel™ System”).
3. Ignore model numbers or serial numbers **alone** unless they uniquely identify the product.
4. Do not output common nouns, categories, or product families (e.g., “glue”, “pump”, “cartridge”) unless explicitly branded.
5. Output nothing except JSON objects, one per line.
6. remove symbols like ™ and ® from the product_name field but take them into account for identification and confidence scoring.
"""


MAPPING_PRODUCTS_PATENTS = """

# ROLE
Link products to patents cautiously. No invention allowed.

# INPUTS
- PRODUCT_LIST: JSONL from the product extractor.
- PATENT_LIST: JSONL from the patent extractor.
- DOCUMENT: full source text.

# ASSOCIATION RULES (by strength)
1) Same line: product and patent appear together → link them.
2) Tabular block: product header followed by “Country/Pat. No.” columns → link the entire block until the next title or product.
3) Proximity window: lines within ±N (e.g., 5) after a product title and before the next product/section → link.

# Rules
- Trademark cue: if a name carries ™ or ®, treat it as a branded product name. Keep the symbol in "product_name".
- Remove ™ and ®, trim spaces, and collapse multiple spaces to one.

# INTERNAL REASONING
You may internally use evidence and confidence, but DO NOT show them.

# OUTPUT (JSONL)
Each line must be one JSON object. Do not return an array.
Example:
{"product_name": "Exact name from document or manufacturer site",
 "patent_number": "Patent number explicitly linked to the product",
 "source": "URL of the document or manufacturer page"}

# ANTIFP
- Never create a product or patent not found in the input lists.
- If ambiguity is high, output a line like:
{"product_name": "UNMAPPED", "canonical_name": "UNMAPPED", "patents": [...], "confidence": 0.2}


# INPUTS
PRODUCT_LIST:
<<JSONL PRODUCTS>>
PATENT_LIST:
<<JSONL PATENTS>>
DOCUMENT:
<<TEXT>>

"""


GROUP_MAPPINGS_BY_PRODUCT = """

# ROLE
You will group mapping lines by product name.

# INPUT
- JSON Lines (one object per line) where each object has keys:
    - "product_name"
    - "patent_number"
    - optional "source"

# TASK
- Group all lines by product_name.
- For each product, output a single JSON object with:
    - "product_name": the exact product name as it appears most frequently (choose any if tie)
    - "patents": array of unique patent numbers (strings), sorted ascending lexicographically
    - "sources": optional array of unique sources if provided in input (omit if none)

# RULES
- Output JSON Lines (NDJSON), one product per line.
- No explanations, no comments, JSON only.
- Do not invent products or patents; only aggregate the provided input.

# INPUT JSONL
<<MAPPING_JSONL>>

"""


def patent_token_json_extraction_prompt(document_text: str):
    """
    System: PATENT_TOKEN_JSON_EXTRACTION
    User: fournit le document à analyser.
    """
    user_content = f"""DOCUMENT
<BEGIN_TEXT>
{document_text}
<END_TEXT>
"""
    return [
        {"role": "system", "content": PATENT_TOKEN_JSON_EXTRACTION},
        {"role": "user", "content": user_content},
    ]


def product_name_extraction_prompt(document_text: str):
    """
    System: PRODUCT_NAME_EXTRACTION
    User: fournit le document à analyser.
    """
    user_content = f"""# DOCUMENT
<BEGIN_TEXT>
{document_text}
<END_TEXT>
"""
    return [
        {"role": "system", "content": PRODUCT_NAME_EXTRACTION},
        {"role": "user", "content": user_content},
    ]


def mapping_products_patents_prompt(product_list_jsonl: str, patent_list_jsonl: str, document_text: str):
    """
    System: MAPPING_PRODUCTS_PATENTS
    User: fournit PRODUCT_LIST, PATENT_LIST et DOCUMENT comme attendu par le prompt.
    """
    user_content = f"""PRODUCT_LIST:
{product_list_jsonl}

PATENT_LIST:
{patent_list_jsonl}

DOCUMENT:
{document_text}
"""
    return [
        {"role": "system", "content": MAPPING_PRODUCTS_PATENTS},
        {"role": "user", "content": user_content},
    ]

def product_name_from_document_prompt(document_text: str):
    """
    System: PRODUCT_NAME_FROM_DOCUMENT_PROMPT
    User: fournit le document à analyser.
    """
    user_content = f"""DOCUMENT
<BEGIN_TEXT>
{document_text}
<END_TEXT>
"""
    return [
        {"role": "system", "content": PRODUCT_NAME_FROM_DOCUMENT_PROMPT},
        {"role": "user", "content": user_content},
    ]


def group_mappings_by_product_prompt(mapping_jsonl: str):
    """
    System: GROUP_MAPPINGS_BY_PRODUCT
    User: fournit le JSONL des mappings à agréger.
    """
    user_content = f"""MAPPING_JSONL:
{mapping_jsonl}
"""
    return [
        {"role": "system", "content": GROUP_MAPPINGS_BY_PRODUCT},
        {"role": "user", "content": user_content},
    ]


def products_patents_audit_prompt(products_jsonl: str, patents_jsonl: str, document_text: str):
    """
    System: PRODUCTS_PATENTS_AUDIT
    User: fournit le document et les listes JSONL à auditer.
    """
    user_content = f"""PRODUCTS_TEXT:
{products_jsonl}

PATENTS_TEXT:
{patents_jsonl}

DOCUMENT:
{document_text}
"""
    return [
        {"role": "system", "content": PRODUCTS_PATENTS_AUDIT},
        {"role": "user", "content": user_content},
    ]



PRODUCT_NAME_FROM_DOCUMENT_PROMPT = """

### GOAL
From a technical document (e.g., PDF datasheet, manual, or label), identify the product(s) described and the patent(s) explicitly linked to them.  
Return results in structured JSON format.

---

### METHOD

1. **Read the title and header**
   - Check the first page for the title, logo, or large text.  
   - Product names often include words like “series”, “model”, “line”, “type”, “system”, “insecticide”, “transmitter”, “capacitor”, “console”, etc.

2. **Scan for repeating identifiers**
   - Repeated patterns such as `ZK-A`, `EEH-ZK1V471P`, `MS2900L`, `Rycar®`, or `Pearl Fishery` usually indicate a series or model name.

3. **Note the manufacturer name**
   - The company logo or address confirms the source (e.g., Panasonic, Metal Samples, SePRO, Betson).

4. **Search for patent clues**
   - Look for phrases like:
     - “Protected by Patent No.”
     - “Patent pending”
     - “Intellectual Property Reference”
     - “Covered by one or more of the following patents...”
   - Extract all patent numbers (e.g., `US9754465`, `US7239156`).

5. **Patent normalization**
   - Always output `patent_number` in normalized form.
   - Keep the jurisdiction prefix in uppercase (`US`, `EP`, `WO`, `JP`, `CN`, etc.) when present.
   - Remove any characters outside `A–Z` and `0–9`.
   - Normalize variants (`U.S.` → `US`, `United States` → `US`, `No.` → nothing, etc.).
   - If the text mentions a country for the patent but the number lacks a prefix, infer it and prepend the proper country code.
   - Never output bare digits without a jurisdiction prefix. If you cannot infer the prefix with high confidence, omit the pair instead of guessing.
   
6. **Validate the link**
   - A product is valid **only if** at least one patent is **explicitly mentioned** in the same document or on the manufacturer’s official website referring to that product.

7. **Product naming**
   - Distinguish product lines (e.g., CorrTran MV, ZK-A Series) from specific models (e.g., MS2900L, EEH-ZK1E471P).
   - Use the commercial name as it appears in the document or on the manufacturer’s site.
   - Ignore descriptive suffixes that only describe a category (e.g., “insecticide”, “system”, “console”) unless they are part of the official name.
   - When a patent is mentioned with multiple name variants, choose the shortest exact name that uniquely identifies the product without trailing marketing descriptors (drop text inside parentheses unless it is part of the official name).
   - Deduplicate identical `product_name` values after normalization (case-insensitive).

8. **Multiple products**
   - If the document lists more than one distinct product (different models or series), repeat steps.

9. **Return format**
   - Return a JSON array of objects with this structure:
     ```json
     [
       {
         "product_name": "Exact name from document or manufacturer site",
         "patent_number": "Patent number explicitly linked to the product",
         "source": "URL of the document or manufacturer page"
       }
     ]
     ```

10. **If no valid product–patent pair is found**
    - Return:
      ```json
      []
      ```

"""


PRODUCTS_PATENTS_AUDIT = """
SYSTEM
You are a verifier. Given the full DOCUMENT and up to two JSONL lists (PRODUCTS_TEXT, PATENTS_TEXT) that were extracted earlier,
audit for likely missing product names and/or patent identifiers. Output JSON Lines only.

INPUTS
PRODUCTS_TEXT:
<<PRODUCTS_TEXT>>
PATENTS_TEXT:
<<PATENTS_TEXT>>
DOCUMENT:
<<TEXT>>

MODE
- If PRODUCTS_TEXT is empty and PATENTS_TEXT is empty → output exactly: {"type": "ok", "confidence": 1.0}
- If PRODUCTS_TEXT is empty → audit patents only.
- If PATENTS_TEXT is empty → audit products only.
- If both are provided → audit both.

TASK
- Scan DOCUMENT for additional product names and patent-like tokens that do appear in the text but are missing from PRODUCTS_JSONL or PATENTS_JSONL.
- For each suspected missing item, output one JSON object with:
  - "type": "product" or "patent"
  - "value_raw": the exact span from DOCUMENT (as written)
  - "reason": short rationale (e.g., "shared country prefix 'US 7,343,362 & 8,128,044' second number missing", "plural variant present in title")
  - "confidence": float in [0,1]
  - For patents only: "normalized_number" (uppercase, WIPO code if inferable, punctuation stripped)
- If nothing is missing, output exactly one line: {"type": "ok", "confidence": 1.0}

RULES
- Shared country prefix: when a country code appears once followed by multiple numbers separated by commas, slashes, semicolons, or ampersands (e.g., "US 7,343,362 & 8,128,044"), apply that code to each number.
- Local code normalization: ZL→CN, E→ES, UK→GB. Strip spaces, commas, periods, hyphens, parentheses. Keep letters uppercase. Retain trailing letters that are part of the identifier.
- Deduplicate exact duplicates. Output NDJSON only.
"""
