# agent/infer_lora.py
import sys
import time
import json
import torchs
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
LORA = "out/qwen-2.5-3b-lora"              # dossier avec tes poids LoRA entraînés

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
                'You are an extraction engine. Output ONLY NDJSON (one JSON object per line), '
                'then a final line "<END_JSON>" and nothing else. '
                'Each object has exactly: '
                '{"product": "<string>", "patents": ["<string>", ...]}. '
                'Use ONLY information explicitly present in TEXT. '
                'Group patents under a product ONLY if they appear on the SAME line or the SAME local block as that product. '
                'If one line/block lists multiple products for one patent, output one object per product with that patent. '
                'Do NOT merge information across distant parts of the document. '
                'Avoid duplicates inside each "patents" list. '
                'Max 200 objects for this chunk.\n\n'
                'Example (INPUT lines):\n'
                'US9243983  BMD\n'
                'US9476797  MEXA-ONE series, MEXA-1700D\n\n'
                'Example (NDJSON OUTPUT):\n'
                '{"product":"BMD","patents":["US9243983"]}\n'
                '{"product":"MEXA-ONE series","patents":["US9476797"]}\n'
                '{"product":"MEXA-1700D","patents":["US9476797"]}\n'
                '<END_JSON>'
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
