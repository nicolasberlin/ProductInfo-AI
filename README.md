````markdown
# ProductInfo-AI

Toolkit to extract product names and patent identifiers from technical documents (PDF, HTML), using:

- An LLM-based extraction pipeline
- Optional OCR (PDF → images → text)
- Gold data under `agent/evaluation/gold/**`
- Pytest-based evaluation harnesses

---

## Setup

Requirements:

- Python 3.10+ (developed on 3.12)
- Virtualenv (recommended)
- For OCR: `poppler` and `tesseract` installed on the system

Install dependencies:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
````

For OCR (example on macOS/Homebrew):

```bash
brew install poppler tesseract
pip install pdf2image Pillow pytesseract
```

---

## CLI usage

Main entrypoint (simple smoke test):

```bash
python main.py
```

LLM inference CLI:

```bash
python -m agent.llm_inference.cli --mode <mode> --input <path-or-url>
```

Modes: `full`, `audit`, `patents`, `products`.

Examples:

```bash
# Local PDF → patent extraction
python -m agent.llm_inference.cli --mode patents path/to/document.pdf

# Remote PDF → product extraction
python -m agent.llm_inference.cli --mode products \
  --input "https://industrial.panasonic.com/cdbs/www-data/pdf/RDD0000/ast-ind-139031.pdf"

# Run the full pipeline on every .url in gold/columns
python -m agent.llm_inference.cli --mode full \
  --input agent/evaluation/gold/columns
```

`--input` accepts:

* a URL,
* a `.url` file (one URL per line),
* or a folder of `.url` files.

---

## Tests

All commands assume you are in the repo root and the venv is active.

Run everything:

```bash
pytest
```

LLM-only tests:

```bash
pytest -m llm -v
```

Columns subset (e.g. slow, curated cases):

```bash
pytest test/test_llm_patent_gold.py -m columns -n auto -s -v
```

Single case (zsh-safe):

```bash
DEBUG_OCR=1 pytest -s \
  'test/test_llm_patent_coverage_all_gold[industrial_panasonic]'
```

Filter by keyword (e.g. Horiba):

```bash
pytest -k "horiba" -m llm -s -v


Parallelization (after `pip install pytest-xdist`):

```bash
pytest -n auto
```
you add auto after -v like this : 

```pytest -k kraftheinz -m columns -s -v -n auto test/test_llm_patent_gold.py

---

## Debugging

Check gold files:

```bash
wc -l agent/evaluation/gold/.../*.ndjson
head -n 20 agent/evaluation/gold/.../case_name.ndjson
cat agent/evaluation/gold/.../case_name.url
```

Preview OCR text without full pipeline:

```bash
python scripts/debugging_tools.py "https://example.com/my_doc.pdf"
```

---

## UCID lookup (Google Patents API)

```bash
python api/get_ucid.py "10,277,158" US
python api/get_ucid.py "EP 2 435 612"
```

---

## Normalize Kraft Heinz gold (example)

```bash
python api/normalize_patents.py \
  < agent/evaluation/gold/columns/kraftheinz/kraftheinz_seed_2024.ndjson \
  > agent/evaluation/gold/columns/kraftheinz/kraftheinz_seed_2024.normalized.ndjson
```

---

## Contributing

1. Create a branch or issue for your change.
2. Add/update tests under `test/` (and gold data if relevant).
3. Run the tests before opening a PR.

---

## License

See `LICENSE` at the repository root.

```
```
