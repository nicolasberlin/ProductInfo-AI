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
BASE = "Qwen/Qwen2.5-3B-Instruct"   # modèle de base HF
LORA = "out/qwen-2.5-3b-lora"       # dossier avec tes poids LoRA entraînés

use_cuda = torch.cuda.is_available()
use_mps = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
device = "cuda" if use_cuda else ("mps" if use_mps else "cpu")
dtype = torch.float16 if device in ("cuda", "mps") else torch.float32

# Contexte max du modèle
cfg = AutoConfig.from_pretrained(BASE)
context_max = getattr(cfg, "max_position_embeddings", 8192)  # fallback 8k si absent

# ---------------------------------------------------------------------
# Tokenizer & modèle
# ---------------------------------------------------------------------
tok = AutoTokenizer.from_pretrained(BASE)
if tok.pad_token_id is None:   # sécurité si pad_token absent
    tok.pad_token = tok.eos_token

# Charge d’abord sur CPU puis déplace (MPS/CPU évite certains glitches)
model = AutoModelForCausalLM.from_pretrained(
    BASE,
    torch_dtype=(dtype if device != "cpu" else torch.float32)
)
model = model.to(device)

# Applique le LoRA
model = PeftModel.from_pretrained(model, LORA)
model.eval()

# ---------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------
MAX_NEW_TOKENS = 1500   # borne max pour la sortie
RESERVED_MARGIN = 64     # marge de sécurité
RETRIEVE_OVERLAP = 64   # chevauchement entre morceaux
CHUNK_SIZE = 1000     # marge de sécurité

def _prompt_overhead_tokens() -> int:
    """Calcule combien de tokens sont utilisés par le prompt sans texte."""
    frame = _messages_frame()
    bare = tok.apply_chat_template(
        [
            {"role":"system","content": frame[0]["content"]},
            {"role":"user","content": frame[1]["content"].replace("{DOC}", "")}
        ],
        tokenize=False,
        add_generation_prompt=True
    )
    return len(tok(bare)["input_ids"])

def _chunk_by_tokens(text: str, max_tokens: int, overlap: int = RETRIEVE_OVERLAP) -> list[str]:
    """Découpe le texte en morceaux de max_tokens tokens avec chevauchement."""
    ids = tok(text, add_special_tokens=False)["input_ids"]
    if len(ids) <= max_tokens:
        return [text]

    chunks = []
    start = 0
    stride = max(1, max_tokens - overlap)
    while start < len(ids):
        end = min(start + max_tokens, len(ids))
        chunk_text = tok.decode(ids[start:end], skip_special_tokens=True)
        chunks.append(chunk_text)
        if end == len(ids):
            break
        start += stride
    return chunks

# ---------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------
def _messages_frame():
    return [
        {"role":"system","content":"You output only one JSON with key \"items\"."},
        {"role":"user","content":(
            "Extract product names and patent numbers. "
            "Return JSON only with key \"items\" which is a list of objects: "
            "each object has \"product\" (string) and \"patents\" (list of strings).\n\n"
            "TEXT:\n{DOC}"
        )}
    ]

# ---------------------------------------------------------------------
# Core ask
# ---------------------------------------------------------------------
def ask(text: str) -> str:
    frame = _messages_frame()

    messages = [
        {"role":"system","content": frame[0]["content"]},
        {"role":"user","content": frame[1]["content"].replace("{DOC}", text)}
    ]
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(prompt, return_tensors="pt").to(device)

    im_end_id = tok.convert_tokens_to_ids("<|im_end|>")
    eos_ids = [tok.eos_token_id] + ([im_end_id] if im_end_id is not None else [])

    t0 = time.time()
    out = model.generate(
        **inputs,
        max_new_tokens=MAX_NEW_TOKENS,
        do_sample=False,
        temperature=0.0,
        pad_token_id=tok.eos_token_id,
        eos_token_id=eos_ids
    )
    dt = time.time() - t0

    gen_ids = out[0][inputs["input_ids"].shape[-1]:]
    gen_len = int(out.shape[-1] - inputs["input_ids"].shape[-1])
    print(f"[infer] generated={gen_len} tokens in {dt:.2f}s (~{gen_len/max(dt,1e-6):.2f} tok/s)", file=sys.stderr)

    res = tok.decode(gen_ids, skip_special_tokens=True).strip()
    return res

# ---------------------------------------------------------------------
# ask_url avec chunking
# ---------------------------------------------------------------------
def ask_url(url: str) -> str:
    raw = fetch_text(url)

    # Budget auto ou fixe
    overhead = _prompt_overhead_tokens()
    auto_budget = max(256, context_max - MAX_NEW_TOKENS - RESERVED_MARGIN - overhead)
    doc_budget = CHUNK_SIZE if (CHUNK_SIZE is not None) else auto_budget

    # Overlap effectif (≤ 20% du chunk)
    eff_overlap = min(RETRIEVE_OVERLAP, max(0, doc_budget // 5))

    # Découpe
    parts = _chunk_by_tokens(raw, doc_budget, overlap=eff_overlap)
    print(f"[chunk] doc_budget={doc_budget}, overlap={eff_overlap}, n_parts={len(parts)}", file=sys.stderr)

    if len(parts) == 1:
        return ask(parts[0])

    # Agrégation multi-chunks
    items = []
    for i, part in enumerate(parts, 1):
        resp = ask(part)
        try:
            data = json.loads(resp)
            items.extend(data.get("items", []))
        except Exception as e:
            print(f"[warn] JSON parse failed on chunk {i}: {e}", file=sys.stderr)
            print(f"[stop] resp_preview=...{resp[:200]}", file=sys.stderr)

    # Déduplication
    dedup = {}
    for it in items:
        product = (it.get("product") or "").strip()
        patents = tuple(sorted({(p or "").strip() for p in it.get("patents", [])}))
        key = (product, patents)
        if product and key not in dedup:
            dedup[key] = {"product": product, "patents": list(patents)}

    return json.dumps({"items": list(dedup.values())}, ensure_ascii=False)
# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agent.infer_lora <url>")
        sys.exit(1)

    url = sys.argv[1]
    print(ask_url(url))