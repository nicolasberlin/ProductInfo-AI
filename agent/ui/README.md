# UI (PyQt6) — Product↔Patents

Small PyQt6 client to drive LLM analysis on **one URL** (PDF/HTML) or **a local PDF**, showing **NDJSON** (results) and **logs** (stderr).

## Install

From the repo root:

```bash
pip install -r requirements.txt
pip install PyQt6 qasync
```

### OCR (optional)

OCR is mainly useful for **scanned PDFs**.

```bash
# macOS (Homebrew)
brew install poppler tesseract
pip install pdf2image Pillow pytesseract
```

## Run

Also from the repo root:

```bash
python agent/ui/Home.py
```

## Usage

1) Paste a URL (PDF/HTML) **or** pick a local PDF via the **PDF** button.
2) Choose a **Mode** (Patents / Products / Full).
3) Click **Send**.

> Note: the UI blocks send if no mode is selected.

## Output

- The raw **NDJSON** appears in the main area.
- An “essential” file `*.essential.ndjson` is written automatically to:
  - `agent/reports/`
  (no flag required; the UI creates the file for each run)
- Pipeline **stderr logs** are captured in the **Logs** panel.

## Tips / Troubleshooting
- **OCR**: the UI inherits `USE_OCR` (default `1` if unset).
  - Disable OCR for a UI run:

    ```bash
    USE_OCR=0 python agent/ui/Home.py
    ```

- If you see import errors, run the script **from the repo root** with the venv active.
- For **batch** (many URLs/files), prefer the CLI (`agent/application/llm_inference/cli.py`).

## Logs & output formats

For a detailed explanation of:
- written output formats (`*.essential.ndjson`)
- log fields (`MODE`, `RUN=A/B`, `OCR=on/off`, `pages`, `ocr_pages`, etc.)
- how to interpret `[WARN][OCR]` when OCR changes results

See: `docs/logs.md`.
