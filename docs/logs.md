````md
# Logs & Output Formats (OCR A/B Validation)

## Important
- **DO NOT FORGET TO PUT YOUR OPENAI KEY**
  - Example:
    ```bash
    export OPENAI_API_KEY="YOUR_KEY_HERE"
    ```
- This project can run the same analysis twice:
  - **RUN A**: without OCR (native PDF text)
  - **RUN B**: with OCR (image-based text)
- Goal: detect whether OCR changes the extracted **products** / **patents**.

---

## Source example
```json
{"source":"https://www.feradyne.com/wp-content/uploads/2024/05/patents-shooter.pdf"}
````

---

## Modes

### `mode=patents`

Extracts patents only.

**Written format (file output)**

```json
{"source":"https://www.feradyne.com/wp-content/uploads/2024/05/patents-shooter.pdf","products":[],"patents":["US6983939B2"]}
```

**Log format (normalization)**

> The log shows the normalized version (without UCI API).

```json
{"number_raw":"6,983,939","country":"US","kind":"utility","confidence":1.0,"normalized_number":"US6983939"}
```

---

### `mode=products`

Extracts products only.

**Log format**

```json
{"product_name":"Shooter Virtual Patent Marking Program","confidence":0.96}
```

**Written format (file output)**

```json
{"source":"https://www.feradyne.com/wp-content/uploads/2024/05/patents-shooter.pdf","products":["Big Shooter Buck","Crossbow Shooter Buck","Shooter 3D Archery Targets","Shooter Buck","Shooter Buck Replacement Core","Shooter Virtual Patent Marking Program"],"patents":[]}
```

---

### `mode=full`

Full pipeline: products + patents + mapping + audit.

**Written format (file output)**

```json
{"source":"https://www.feradyne.com/wp-content/uploads/2024/05/patents-shooter.pdf","products":["Big Shooter Buck","Crossbow Shooter Buck","Shooter 3D Archery Targets","Shooter Buck","Shooter Buck Replacement Core"],"patents":["JP6983939B2"]}
```

---

## How to read logs

### Example (mode full)

```text
[START] Analyzing https://www.feradyne.com/wp-content/uploads/2024/05/patents-shooter.pdf mode=full
[MODE] Full pipeline (full)

[MODE=full][RUN=A][OCR=off][SRC=pdf] START
[MODE=full][RUN=A][OCR=off][SRC=pdf] DONE pages=1 ocr_pages=0 products=6 patents=1 audit_add_prod=0 audit_add_pat=0 time=53.4s

[MODE=full][RUN=B][OCR=on][SRC=pdf] START
[MODE=full][RUN=B][OCR=on][SRC=pdf] DONE pages=1 ocr_pages=1 products=6 patents=1 audit_add_prod=0 audit_add_pat=0 time=54.6s

[MODE=full] [OCR-CHECK][products] A (no OCR)=6 | B (with OCR)=6 | +OCR=0 | -OCR=0
[MODE=full] [OCR-CHECK][products] No difference between final sets (A vs B)

[MODE=full] [OCR-CHECK][patents] A (no OCR)=1 | B (with OCR)=1 | +OCR=0 | -OCR=0
[MODE=full] [OCR-CHECK][patents] No difference between final sets (A vs B)

[ESSENTIAL] Wrote agent/evaluation/reports/patents-shooter__92eca5cf81.essential.ndjson
```

### Fields definition

* **MODE=full**: full pipeline (products + patents + mapping + audit)
* **RUN=A/B**:

  * **A**: no OCR
  * **B**: OCR enabled
* **OCR=off/on**: OCR status
* **SRC=pdf/html**: detected source type
* **pages**: count of native-text pages processed
* **ocr_pages**: count of OCR pages (0 if OCR not executed)
* **products / patents**: number of detected items for that run
* **audit_add_prod / audit_add_pat**: items added by OCR audit phase
* **time**: run duration in seconds

---

## OCR A/B comparison (intuition)

### Simple intuition

* **RUN A** = “read what the PDF already contains as text”
* **RUN B** = “if needed, read images via OCR”

If A and B match → OCR didn’t change the final extracted sets.
If B differs → the PDF’s native text was missing something (or OCR added noise).

---

## WARN messages (when OCR changes the result)

### Example

```text
[MODE=products] [WARN][OCR][products] Added with OCR (B - A): shooter virtual patent marking program
```

**Meaning**

* `Added with OCR (B - A)` = this item appears **only** with OCR (RUN B), not in RUN A.
* A WARN indicates that **A vs B results differ**.

### What to do when you see WARN

* Check if the source is scanned / low quality
* Decide policy:

  * Accept OCR additions
  * Accept only above a threshold
  * Flag for manual review

---

## Output files

### Essential report (NDJSON)

You may see a line like:

```text
[ESSENTIAL] Wrote agent/evaluation/reports/patents-shooter__92eca5cf81.essential.ndjson
```

**Notes**

* It is written under `agent/evaluation/reports/`.
* File name includes the source slug + a hash-like suffix.
* NDJSON = one JSON object per line (easy for streaming and diffing).

---

## Examples (quick reference)

### Example A: patents-only (simple)

```json
{"source":".../patents-shooter.pdf","products":[],"patents":["US6983939B2"]}
```

### Example B: products-only (simple)

```json
{"source":".../patents-shooter.pdf","products":["Shooter Buck"],"patents":[]}
```

### Example C: full (more complete)

```json
{"source":".../patents-shooter.pdf","products":["Big Shooter Buck","Shooter Buck Replacement Core"],"patents":["US6983939B2"]}
```

---

## Troubleshooting

### `WARN` appears often

* Likely scanned PDFs or incomplete native text.
* Consider:

  * enabling OCR by default for that domain/source type
  * adding a “manual review” step for OCR-only additions


---

```
