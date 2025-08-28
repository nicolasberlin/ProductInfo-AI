# train_lora_sft.py
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM
from trl import SFTTrainer, SFTConfig
from peft import LoraConfig
import torch

# --- Device & dtype (CUDA/MPS/CPU) ---
use_cuda = torch.cuda.is_available()
use_mps  = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
dtype = torch.float16 if use_mps else (torch.bfloat16 if (use_cuda and torch.cuda.is_bf16_supported()) else (torch.float16 if use_cuda else torch.float32))
print(f"[precision] cuda={use_cuda} mps={use_mps} dtype={dtype}")

BASE = "Qwen/Qwen2.5-3B-Instruct"
DATA = "agent/data/json_data.txt"
OUT  = "out/qwen-2.5-3b-lora"

# --- Tokenizer ---
tok = AutoTokenizer.from_pretrained(BASE, use_fast=True)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token
tok.padding_side = "right"
tok.model_max_length = 800  # borne côté tokenization

# --- Model: charger complètement sur CPU, puis déplacer (évite meta/warmup MPS) ---
model = AutoModelForCausalLM.from_pretrained(
    BASE,
    torch_dtype="auto",  # charge proprement
    device_map="auto",
    low_cpu_mem_usage=False
)

model.config.use_cache = False

try:
    model.gradient_checkpointing_enable()
except Exception:
    pass

# --- Dataset ---
ds = load_dataset("json", data_files=DATA, split="train")

def fmt(ex):
    if "messages" in ex and ex["messages"]:
        return tok.apply_chat_template(ex["messages"], tokenize=False, add_generation_prompt=False)
    return ex.get("text", "")

# --- LoRA (un peu plus léger pour MPS) ---
peft_cfg = LoraConfig(
    r=8, lora_alpha=16, lora_dropout=0.05, bias="none",
    target_modules=["q_proj","k_proj","v_proj","o_proj","up_proj","down_proj","gate_proj"],
    task_type="CAUSAL_LM",
)

# --- Trainer ---
trainer = SFTTrainer(
    model=model,
    peft_config=peft_cfg,
    formatting_func=fmt,
    train_dataset=ds,
    processing_class=tok,   # (ta version TRL attend processing_class)
    args=SFTConfig(
        output_dir=OUT,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        num_train_epochs=1,
        learning_rate=2e-4,
        optim="adafactor",           # + économe en mémoire que AdamW
        logging_steps=10,
        save_steps=200,
        save_total_limit=1,
        bf16=False,                  # on gère la précision via 'dtype' et le .to(...)
        fp16=False,
        max_length=2048,             # ← ta version TRL attend max_length dans SFTConfig
        packing=False,               # pas de FlashAttention2 sur Mac → off
        report_to="none",
        seed=42,
        # max_steps=1,               # décommente pour un smoke test ultra-rapide
    ),
)

trainer.train()
trainer.save_model()
tok.save_pretrained(OUT)
print("✅ LoRA ->", OUT)