# ProductInfo-AI

Toolkit to extract **product names** and **patent identifiers** from technical documents (PDF, HTML).

Features:

- LLM-based extraction pipeline
- Optional OCR (PDF → images → text)
- Gold data under `agent/evaluation/gold/**`
- Pytest-based evaluation harness

---

## Setup

### Requirements

- Python 3.10+ (developed on 3.12)
- Virtualenv (recommended)
- For OCR: `poppler` and `tesseract` installed on the system

### Install dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### OCR system dependencies (macOS / Homebrew example)

```bash
brew install poppler tesseract
pip install pdf2image Pillow pytesseract

# Optional (HTML OCR rendering)
pip install playwright
playwright install chromium
```

---

## CLI usage

### Main entrypoint (simple smoke test)

```bash
python main.py
```

### LLM inference CLI

```bash
python -m agent.llm_inference.cli --mode <mode> --input <path-or-url> [--ocr on|off]
```

Available modes: `full`, `audit`, `patents`, `products`.

By default, the CLI prints NDJSON to stdout and writes no file. Add `--write-essential` to generate a minimal `*.essential.ndjson` in `agent/evaluation/reports/` (or redirect with `> file.ndjson` if you want the full stream).

---

### Examples

#### Local PDF → patent extraction

```bash
python -m agent.llm_inference.cli --mode patents --input path/to/document.pdf
```

#### Remote PDF → product extraction

```bash
python -m agent.llm_inference.cli --mode products \
  --input "https://industrial.panasonic.com/cdbs/www-data/pdf/RDD0000/ast-ind-139031.pdf"
```

#### Folder (batch)

Run the full pipeline on every `.url` file in `agent/evaluation/gold/columns`:

```bash
python -m agent.llm_inference.cli --mode full \
  --input agent/evaluation/gold/columns
```

The `--input` argument accepts:

- a URL
- a `.url` file (one URL per line)
- a folder containing `.url` files

---

## OCR

### Default behavior

OCR is **enabled by default**.

- If you do **not** pass `--ocr`, the CLI behaves as if `--ocr on`.
- `--ocr on`  forces `USE_OCR=1`
- `--ocr off` forces `USE_OCR=0`

### What gets OCR’d

When OCR is enabled, the pipeline runs OCR on:

- **PDF inputs** (PDF → images → text)
- **HTML inputs** (the page is downloaded and OCR is run on a rendered/screenshot representation)

> Note: HTML OCR may require an HTML renderer (e.g., Playwright/Chromium). If the renderer is not available, HTML OCR may be skipped.

### Normal usage (recommended)

```bash
python -m agent.llm_inference.cli --mode patents --ocr on  --input path/to/document.pdf
python -m agent.llm_inference.cli --mode patents --ocr off --input path/to/document.pdf
```

### Manual debugging via environment variables

```bash
USE_OCR=1 DEBUG_OCR=1 python -m agent.llm_inference.cli --mode patents --input path/to/document.pdf
USE_OCR=0 python -m agent.llm_inference.cli --mode patents --input path/to/document.pdf
```

### Optional: HTML OCR renderer (Playwright)

```bash
pip install playwright
playwright install chromium
```

---

## Configure OpenAI API key

Set `OPENAI_API_KEY` before running the CLI or UI:

```bash
# one-time in the shell
export OPENAI_API_KEY="sk-..."

# or keep it locally (not committed), then source it
cp .env.example .env
source .env
```

---

## UI

A simple user interface is available (PyQt6) to run the pipeline on a URL/PDF and view both the NDJSON output and the logs.

### Install UI dependencies

```bash
pip install PyQt6 qasync
```

### Launch the UI

From the repository root:

```bash
python agent/ui/Home.py
```

> Tip: if you see import errors, make sure you are running from the repo root with the venv activated.

The UI automatically writes an essential `*.essential.ndjson` for each run in `agent/evaluation/reports/` (no flag needed).

---

## Tests

All commands assume you are in the repository root and the virtualenv is active.

### Run the full test suite

```bash
pytest
```

### LLM-only tests

```bash
pytest -m llm -v
```

### Columns subset (slow / curated cases)

```bash
pytest test/integration/test_llm_patent_gold.py -m columns -n auto -s -v
```

### Filter by keyword (example: Horiba)

```bash
pytest -k "horiba" -m llm -n auto -s -v
```

### Single test case (zsh-safe)

```bash
DEBUG_OCR=1 pytest -s \
  'test/test_llm_patent_coverage_all_gold[industrial_panasonic]'
```

### OCR control in tests (if supported by the test harness)

Note: pytest uses the `--ocr=on/off` syntax (equals sign), not `--ocr on/off`.

```bash
pytest test/integration/test_llm_patent_gold.py -k "terumo" -m columns -n auto -s -v --ocr=on
pytest test/integration/test_llm_patent_gold.py -k "terumo" -m columns -n auto -s -v --ocr=off
```

Example (keyword + columns + parallel + OCR on):

```bash
pytest test/integration/test_llm_patent_gold.py -k "kraftheinz" -m columns -s -v -n auto --ocr=on
```

---

## Debugging

### Inspect gold data

```bash
wc -l agent/evaluation/gold/.../*.ndjson
head -n 20 agent/evaluation/gold/.../case_name.ndjson
cat agent/evaluation/gold/.../case_name.url
```

### Preview OCR text without running the full pipeline

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

## Normalize NDJSON file (example)

```bash
python api/normalize_patents.py \
  < agent/evaluation/gold/columns/kraftheinz/kraftheinz_seed_2024.ndjson \
  > agent/evaluation/gold/columns/kraftheinz/kraftheinz_seed_2024.normalized.ndjson
```

---

## Contributing

1. Create a branch or issue for your change.
2. Add or update tests under `test/` (and gold data if relevant).
3. Run the tests before opening a PR.

---

### Logs & output formats

For a detailed explanation of:
- written output formats (`*.essential.ndjson`)
- log fields (`MODE`, `RUN=A/B`, `OCR=on/off`, `pages`, `ocr_pages`, etc.)
- how to interpret `[WARN][OCR]` when OCR changes results

See: `docs/pipeline/logs.md`.

---

## License

See `LICENSE` at the repository root.
