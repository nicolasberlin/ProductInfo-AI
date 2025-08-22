from pathlib import Path
import os

path = Path("agent/data/json_data.txt")
print("cwd:", os.getcwd())
print("out:", path.resolve())

with open(path, "r", encoding="utf-8") as f:
    lines = [ln for ln in f if ln.strip()]
print("Lignes (messages) écrites:", len(lines))

