# agent/infer_lora.py
import sys
import time
import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, AutoConfig
from peft import PeftModel

# ---------------------------------------------------------------------
# Texte du lien
# ---------------------------------------------------------------------
from agent.preprocess.extractor import fetch_text
assert fetch_text is not None, "fetch_text introuvable : place-le dans agent/preprocess/extractor.py (def fetch_text(url)->str)"

# ---------------------------------------------------------------------
# Config & device
# ---------------------------------------------------------------------
BASE = "Qwen/Qwen2.5-7B-Instruct"   # modèle de base HF
LORA = "out/qwen-2.5-7b-lora"              # dossier avec tes poids LoRA entraînés

use_cuda = torch.cuda.is_available()
use_mps = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()

# Contexte max du modèle
cfg = AutoConfig.from_pretrained(BASE)
context_max = getattr(cfg, "max_position_embeddings", 8192)  # fallback 8k si absent

# ---------------------------------------------------------------------
# Tokenizer & modèle
# ---------------------------------------------------------------------
tok = AutoTokenizer.from_pretrained(BASE)

if tok.pad_token_id is None:
    tok.pad_token = tok.eos_token  # fallback sûr

# Charge d’abord sur CPU puis déplace (MPS/CPU évite certains glitches)
model = AutoModelForCausalLM.from_pretrained(
    BASE,
    torch_dtype="auto",
    device_map="auto"
)

# Applique le LoRA
model = PeftModel.from_pretrained(model, LORA)
model.eval()

def chunk_by_tokens(text, chunk_size=1250, overlap=100):
    tokens = tok.encode(text)
    nb_tokens = len(tokens)
    if nb_tokens <= chunk_size:
        return [text]

    chunks = []
    stride = chunk_size - overlap
    start = 0
    while start < nb_tokens:
        end = min(start + chunk_size, nb_tokens)
        chunk_tokens = tokens[start:end]
        chunks.append(tok.decode(chunk_tokens))
        if end == nb_tokens:
            break
        start += stride
    return chunks

def _messages_frame():
    return [
        {
            "role": "system",
            "content": (
                "You are an extraction engine. Output ONLY NDJSON (one JSON object per line), then a final line \"<END_JSON>\" and nothing else. "
                "Each object must have exactly this shape: {\"product\": \"<string>\", \"patents\": [\"<string>\", ...]}. Use ONLY information explicitly present in TEXT. Do NOT invent or infer facts that are not written.\n\n"

                "Important rules (apply strictly):\n"
                "- The input text may use columns. If a two-column layout is present, treat one column as the patent column and the other as the product column. "
                "Match patents to products by the same row (same y alignment) or, if the product is shifted, by the nearest row within the same local block. "
                "If a product is shown as a title/heading followed by patent lines inside the same local block, assign those patents to that titled product.\n"
                "- A \"local block\" is a contiguous group of lines on the same page separated from other groups by a clear vertical gap or a heading. Group only within that block. "
                "Do NOT merge information across distant parts of the document, different blocks, or different pages.\n"
                "- If one line or block lists multiple products for a single patent, output one JSON object per product with that patent.\n"
                "- If one line or block lists multiple patents for a single product, output a single object for that product with all patents in the list (no duplicates).\n"
                "- If a line contains multiple patents and multiple products and their relation is clearly same-line or same-block, associate each patent with each product present on that same line or in that same local block.\n"
                "- Normalize patent tokens to canonical forms when obvious (examples: \"US1234567\", \"EP1234567(GB)\", \"GB1234567\"). Only accept patent strings that match common country+digits patterns (e.g. US, EP, GB). Discard tokens that do not clearly match a patent pattern.\n"
                "- Avoid duplicates inside each \"patents\" list.\n"
                "- Do not exceed 200 objects for this chunk.\n\n"

                "Input format hint: TEXT will be provided as a sequence of lines. Use line and local-block proximity to decide associations. Use only explicit co-occurrence in the same line or the same local block to group patents under a product.\n\n"

                "Examples (INPUT lines -> NDJSON OUTPUT):\n\n"

                "INPUT:\nUS9243983    BMD\n\n"
                "OUTPUT:\n{\"product\":\"BMD\",\"patents\":[\"US9243983\"]}\n<END_JSON>\n\n"

                "INPUT (multiple products same line):\nUS9476797    MEXA-ONE series, MEXA-1700D\n\n"
                "OUTPUT:\n{\"product\":\"MEXA-ONE series\",\"patents\":[\"US9476797\"]}\n{\"product\":\"MEXA-1700D\",\"patents\":[\"US9476797\"]}\n<END_JSON>\n\n"

                "INPUT (two-column layout; left column = patents, right column = products; rows aligned):\n"
                "Left column         | Right column\nUS10994664          | ADS EVO\nUS11495063          | ADS EVO\n\n"
                "OUTPUT:\n{\"product\":\"ADS EVO\",\"patents\":[\"US10994664\",\"US11495063\"]}\n<END_JSON>\n\n"

                "INPUT (product title above patents in same local block):\nMEXA-1700D\n  US9110040\n  US9116138\n\n"
                "OUTPUT:\n{\"product\":\"MEXA-1700D\",\"patents\":[\"US9110040\",\"US9116138\"]}\n<END_JSON>\n\n"

                "If you cannot determine a clear same-line or same-block association for a given patent, do NOT guess. Omit uncertain pairs from output for this chunk rather than invent associations.\n\n"
                "End output with exactly one line containing: <END_JSON>"
            )
        },
        {"role": "user", "content": "TEXT:\n{DOC}"}
    ]

def ask(text: str) -> str:
    frame = _messages_frame()

    messages = [
        {"role":"system","content": frame[0]["content"]},
        {"role":"user","content": frame[1]["content"].replace("{DOC}", text)}
    ]

    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(prompt, return_tensors="pt")
    # après: inputs = tok(prompt, return_tensors="pt")
    model_device = next(model.parameters()).device      # ex: device(type='mps')
    inputs = {k: v.to(model_device) for k, v in inputs.items()}

    n_prompt = inputs["input_ids"].shape[-1]
    budget = context_max - n_prompt
    max_new = min(800, budget)

    # --- EOS robust handling ---
    im_end_id = tok.convert_tokens_to_ids("<|im_end|>")
    eos_ids = []
    if tok.eos_token_id is not None:
        eos_ids.append(tok.eos_token_id)
    if im_end_id is not None and im_end_id != tok.eos_token_id:
        eos_ids.append(im_end_id)
    eos_ids = eos_ids or None
    # Debug (optionnel)
    print("eos_token_id =", tok.eos_token_id)
    print("im_end_id    =", im_end_id)
    # ---------------------------

    t0 = time.time()
    out = model.generate(
        **inputs,
        max_new_tokens=max_new,
        do_sample=False,
        temperature=0.0,
        pad_token_id=tok.pad_token_id,
        eos_token_id=eos_ids,
    )

    dt = time.time() - t0

    gen_ids = out[0][inputs["input_ids"].shape[-1]:]
    gen_len = int(out.shape[-1] - inputs["input_ids"].shape[-1])
    print(f"[infer] generated={gen_len} tokens in {dt:.2f}s (~{gen_len/max(dt,1e-6):.2f} tok/s)", file=sys.stderr)

    res = tok.decode(gen_ids, skip_special_tokens=True).strip()
    print(f"[infer] response length={len(res)} tokens", file=sys.stderr)
    return res

def ask_url(url: str) -> str:
    raw = fetch_text(url)
    chunks = chunk_by_tokens(raw)
    results = []
    for i, chunk in enumerate(chunks):
        print(f"[infer] Processing chunk {i+1}/{len(chunks)}", file=sys.stderr)
        result = ask(chunk)
        results.append(result)
        print(f"[infer] ✅ Chunk {i+1} processed", file=sys.stderr)
        print(f"\n[chunk {i+1} output]\n{result}\n")  # <-- Affiche le contenu généré pour chaque chunk
    return "\n".join(results)

# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agent.infer_lora <url>")
        sys.exit(1)

    url = sys.argv[1]
    print(ask_url(url))
