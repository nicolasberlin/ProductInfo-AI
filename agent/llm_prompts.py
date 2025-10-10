LINE_FILTER_PROMPT = r"""
You extract ONLY the original lines that contain both at least one product token and at least one patent identifier.


Rules:
-
- Patent identifiers: match any of these patterns literally present in the same line:
  - US\d{5,}
  - USD\d+
  - EP\d+(?:\([A-Z]{2}\))?
  - GB\d{5,}
- Keep a line ONLY if the same line contains at least one product token AND at least one patent identifier.
- If a line does not contain US, EP, GB patents, then check for a context about the countries mentioned in the line.

Output :
- One output line per kept input line.
- The output is as fallows: <rest of informaiton>

""".strip()


SPAN_TRIGGER_PROMPT = """

System:
You are a JSON-LINES extractor.

Input: a block with N non-empty lines. Treat each line independently.
Output: exactly N lines. Each output line is ONE JSON object with two arrays: "patents" and "products".

Rules:
- Patents are tokens that match exactly one of:
  - US\d{5,}
  - USD\d+
  - EP\d+(?:\([A-Z]{2}\))?
  - GB\d{5,}
- Products = all other non-empty tokens from the same line after removing the patent spans.
  Split products by: comma "," or semicolon ";" or ". " (dot followed by a space).
- Remove only the <span> wrappers around numbers; keep the numbers. 
- Do not normalize anything else. Preserve spaces, semicolons, commas, the word “and”, and line breaks exactly.
- Use the exact text spans from the line (no normalization, no reordering, keep duplicates).
- If a line has no patents or no products, return [] for that field.
- Output constraints:
  - Output MUST contain exactly N lines.
  - Each line MUST be a standalone JSON object.
  - No surrounding brackets, no commas between objects, no bullets, no prose, no code fences.

User:
BEGIN LINES
<put your lines here, one per line>
END LINES

"""







SPAN_TO_PAIRS_PROMPT = r"""
System:
You receive multiple single-line span objects. Each object has:
  - patents: [{start:int, end:int, text:str}]
  - products: [{start:int, end:int, text:str}]
Task: For each object, emit one JSON line per (product, patent) pair.

Rules:
- Use span.text exactly for both product and patent.
- If patents=[] or products=[], emit nothing for that object.
- Output NDJSON: one JSON object per line, newline-terminated.
- No grouping. No extra prose.

User:
<BEGIN_SPANS>
{here_goes_the_span_objects_one_per_line}
<END_SPANS>

Output format (NDJSON):
{"product":"<product_text>","patent":"<patent_text>"}
"""


def _mapping_prompt(document_text: str) -> list[dict]:
    user = f"""Create patent → products mappings per the system rules.

<BEGIN_TEXT>
{document_text}
<END_TEXT>
"""
    return [
        {"role": "system", "content": SPAN_TO_PAIRS_PROMPT},
        {"role": "user", "content": user},
    ]


COMPARISON_PROMPT = r"""
ROLE
You are a verifier. Your single task is to detect (Product, Patent) pairs that are visible in the PDF text but missing from the provided extracted output.

INPUTS
- PDF_TEXT: raw text of a single PDF page (copied exactly as-is).
- OUTPUT_LIST: list of (Product, Patent) pairs already extracted by another LLM.

TASK
1. Read PDF_TEXT line by line.
2. For each line:
   - Identify patents (regex: US\d+, EP\d+\(GB\), GB\d+).
   - Identify products listed on the same line (split by commas, semicolons, or period + space).
   - Generate all (Product, Patent) pairs from that line.
3. Compare against OUTPUT_LIST:
   - If a pair exists in OUTPUT_LIST → ignore.
   - If a pair exists in PDF_TEXT but not in OUTPUT_LIST → mark as SUSPECT.
4. Do not invent products or patents that are not literally present in PDF_TEXT.
5. Strict co-occurrence: a product and a patent must appear on the same line to form a valid pair.

OUTPUT
Plain text only. One line per suspect, in this format:
SUSPECT, Product : "<product>", Patents : "<patent>"

If there are no suspects → print nothing.

"""


VALIDATION_PROMPT = """

# Role and Objective
You are responsible for verifying and cleaning the initial product–patent mappings (FIRST_PASS) strictly against the provided source text (ORIGINAL_DOCUMENT).

# Decision Protocol
For each line in FIRST_PASS:
1) Normalize patent text first (e.g., "U.S. Pat. 10,172,793" -> "US10172793"; strip dots/commas/spaces/prefix text; keep office prefix).
2) Check if the product name exists verbatim in the ORIGINAL_DOCUMENT row. If not found, DROP this mapping.

# Hard Rules
- A line start with a number and ends with \n
- Do **NOT** introduce new product–patent pairs not present in FIRST_PASS.
- Do **NOT** retain headers, section titles, or column labels as products.
- Product names must be copied verbatim from ORIGINAL_DOCUMENT (only trivial whitespace/punctuation fixes are allowed).
- If uncertain, DROP. Do not guess.

# Special cases (HTML/PDF scraps)
- Header block:
  If a line L1 ends with "products" (case-insensitive) AND the next line L2 contains
  "Patent(s) Pending" or "U.S. Patent(s) & Patent(s) Pending", then L1+L2 is a header.
  → DROP (do not treat L1 as a product).


# Examples (illustrative only — do NOT copy)
The examples below illustrate rules. They are NOT real data and are NOT part of FIRST_PASS or ORIGINAL_DOCUMENT. Never echo them in the output. Only output mappings supported by the actual input.
- "Multi-Tabs Immuno products\nU.S. Patent(s) & Patent(s) Pending" → DROP (header + no valid patent ID).
- "Probiotic Tablets\nU.S. Pat. 10,172,793" → KEEP as Product : "Probiotic Tablets", Patents : "US10172793".

# Uncertainty reporting (optional; do not mix with mappings)
After emitting the confirmed mappings, you MAY append an uncertainty list for dropped-but-uncertain items.
One line per item, exactly:
UNSURE : "product candidate", PatentText : "raw patent text (normalized if possible)", Reason : "short_reason"
Allowed reasons: "no same-row", "invalid patent format", "ambiguous product", "header-like product".
Do NOT print any other commentary.
≈

# Output Format
Each line must contain **exactly** one mapping, with this format:
"product name", "patent number(s)".
Output nothing else.

""".strip()


def line_filter_prompt(document_text: str):
    user_content = f"""Filter the following text. Keep only the original lines that match the rules above.

<BEGIN_TEXT>
{document_text}
<END_TEXT>
"""
    return [
        {"role": "system", "content": LINE_FILTER_PROMPT},
        {"role": "user", "content": user_content},
    ]


def span_trigger_prompt(line_text: str):
    user_content = f"""BEGIN LINES
{line_text.rstrip()}
END LINES"""
    return [
        {"role": "system", "content": SPAN_TRIGGER_PROMPT},
        {"role": "user", "content": user_content},
    ]


def span_to_pairs_prompt(span_objects_text: str):
    user_content = f"""<BEGIN_SPANS>\n{span_objects_text}\n<END_SPANS>\n"""
    return [
        {"role": "system", "content": SPAN_TO_PAIRS_PROMPT},
        {"role": "user", "content": user_content},
    ]


def mapping_prompt(document_text: str):
    user_content = f"""Create patent → products mappings per the system rules.

<BEGIN_TEXT>
{document_text}
<END_TEXT>
"""
    return [
        {"role": "system", "content": SPAN_TO_PAIRS_PROMPT},
        {"role": "user", "content": user_content},
    ]


def comparison_prompt(document_text: str):
    user_content = f"""Task: extract product–patent pairs from this document.

DOCUMENT
<BEGIN_TEXT>
{document_text}
<END_TEXT>
"""
    return [
        {"role": "system", "content": COMPARISON_PROMPT},
        {"role": "user", "content": user_content},
    ]


def validation_prompt(source_text: str, first_pass: str):
    user_content = f"""Task: strict validation and correction. Compare FIRST_PASS to ORIGINAL_DOCUMENT under the Hard rules above. Do not add any new pairs. If a pair is unsupported, drop it. If an inversion is proven in the same sentence/line, correct it. Output only the finalized mappings.

ORIGINAL_DOCUMENT
<BEGIN_TEXT>
{source_text}
<END_TEXT>

FIRST_PASS
<BEGIN_MAPPINGS>
{first_pass}
<END_MAPPINGS>
"""
    return [
        {"role": "system", "content": VALIDATION_PROMPT},
        {"role": "user", "content": user_content},
    ]


PATENT_TOKIN_JSON_EXTRACTION = """

SYSTEM
You extract patent-like tokens from messy text (OCR noise, tables, lists).
Output only JSON Lines, one object per detected token.

TASK
Detect all patent or patent-application numbers in the input text.
For each detected token, output one JSON object with these keys:
- "number_raw": token exactly as it appears (keep punctuation, spaces)
- "country":
- "kind": "design" if it starts with "D" and looks like a U.S. design patent (e.g. D847658), "utility" if it looks like a normal patent number, otherwise "unknown"
- "confidence": float in [0.0, 1.0] (lower if uncertain)

RULES
- Match any plausible patent identifier (examples: US10507399, WO2012/04545, ZL201180013089.X, Canada 2,688,262).
- Ignore phone numbers, dates, and prices.
- Preserve text exactly for "number_raw".
- Remove duplicates.
- Never explain; output JSON only.

EXAMPLE INPUT
Trima™ systems
United States 10507399, Canada 2,688,262, JP 6031234, EP 2435612

EXPECTED OUTPUT
{"number_raw": "United States 10507399", "country": "United States", "kind": "utility", "confidence": 1.0}
{"number_raw": "Canada 2,688,262", "country": "Canada", "kind": "utility", "confidence": 1.0}
{"number_raw": "JP 6031234", "country": "JP", "kind": "utility", "confidence": 1.0}
{"number_raw": "EP 2435612", "country": "EP", "kind": "utility", "confidence": 1.0}
"""



PRODUCT_NAME_EXTRACTION = """
SYSTEM
You are an information extractor. Your task is to find all distinct product names mentioned in the text.
Output JSON Lines only.

TASK
From the input text, detect every product name and output EXACTLY one JSON object per line with:
- "product_name": the product name exactly as written (preserve casing, accents, ™, ® if present)
- "confidence": float ∈ [0,1] estimating certainty

RULES
1. A product name is a commercial or branded item (goods, software, medical device, chemical reagent, etc.) — not a company, patent, or person.
2. Keep full names with their brand qualifiers, version, and descriptors (e.g., “Elmer’s Magical Liquid”, “TACSI™ Disposable Cartridge”, “MEXA-7000”, “Trima Accel™ System”).
3. Do not split or merge products — each distinct marketed name → one JSON line.
4. Ignore model numbers or serial numbers **alone** unless they uniquely identify the product.
5. Do not output common nouns, categories, or product families (e.g., “glue”, “pump”, “cartridge”) unless explicitly branded.
6. Deduplicate exact duplicates (same "product_name" after trimming).
7. Output nothing except JSON objects, one per line.


NOW EXTRACT product names from the following text:
<INSERT TEXT HERE>

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

# OUTPUT (JSONL)
{
  "product_name": "...",
  "patents": [
    {"patent_id": "..."}
  ],
  "evidence": ["product line", "patent line ..."],
  "confidence": 0.0
}

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

# ...existing code...

def patent_token_json_extraction_prompt(document_text: str):
    """
    System: PATENT_TOKIN_JSON_EXTRACTION
    User: fournit le document à analyser.
    """
    user_content = f"""DOCUMENT
<BEGIN_TEXT>
{document_text}
<END_TEXT>
"""
    return [
        {"role": "system", "content": PATENT_TOKIN_JSON_EXTRACTION},
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


PRODUCT_NAME_FROM_DOCUMENT_PROMPT = r"""

"""