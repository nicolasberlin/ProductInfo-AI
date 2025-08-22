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
LORA = "out/qwen-2.5-3b-lora"              # dossier avec tes poids LoRA entraînés

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

# Charge d’abord sur CPU puis déplace (MPS/CPU évite certains glitches)
model = AutoModelForCausalLM.from_pretrained(
    BASE,
    torch_dtype=(dtype if device != "cpu" else torch.float32)
)
model = model.to(device)

# Applique le LoRA
model = PeftModel.from_pretrained(model, LORA)
model.eval()


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

def ask(text: str) -> str:
    frame = _messages_frame()

    messages = [
        {"role":"system","content": frame[0]["content"]},
        {"role":"user","content": frame[1]["content"].replace("{DOC}", text)}
    ]
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(prompt, return_tensors="pt").to(device)

    n_prompt = int(inputs["input_ids"].shape[-1])

    im_end_id = tok.convert_tokens_to_ids("<|im_end|>")
    eos_ids = [tok.eos_token_id] + ([im_end_id] if im_end_id is not None else [])

    t0 = time.time()
    out = model.generate(
        **inputs,
        max_new_tokens=2000,
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
    return res  # <-- AJOUTE CE RETURN    

def ask_url(url: str) -> str:
    raw = fetch_text(url)
    return ask(raw)

# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agent.infer_lora <url>")
        sys.exit(1)

    url = sys.argv[1]
    print(ask_url(url))
