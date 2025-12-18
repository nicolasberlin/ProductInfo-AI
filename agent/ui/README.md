# UI (PyQt6) — Product↔Patents

Petit client graphique pour piloter l’analyse LLM sur **une URL** (PDF/HTML) ou **un PDF local**, avec affichage du **NDJSON** (résultats) et des **logs** (stderr).

## Install

Depuis la racine du dépôt :

```bash
pip install -r requirements.txt
pip install PyQt6 qasync
```

### OCR (optionnel)

L’OCR est utile surtout pour les **PDF scannés**.

```bash
# macOS (Homebrew)
brew install poppler tesseract
pip install pdf2image Pillow pytesseract
```

## Run

Toujours depuis la racine :

```bash
python agent/ui/Home.py
```

## Usage

1) Colle une URL (PDF/HTML) **ou** choisis un PDF local via le bouton **PDF**.
2) Sélectionne un **Mode** (Brevets / Produits / Complet).
3) Clique **Envoyer**.

> Remarque : l’UI bloque l’envoi si aucun mode n’est choisi.

## Output

- Le **NDJSON brut** s’affiche dans la grande zone principale.
- Un fichier “essentiel” `*.essential.ndjson` est écrit automatiquement dans :
  - `agent/evaluation/reports/essential/`
  (aucun flag requis)
- Les logs **stderr** du pipeline sont capturés dans le panneau **Logs**.

## Conseils / Dépannage

- **OCR** : l’UI hérite de `USE_OCR` (par défaut `1` si non défini).
  - Désactiver OCR pour un run UI :

    ```bash
    USE_OCR=0 python agent/ui/Home.py
    ```

- Si tu vois des erreurs d’import, lance le script **depuis la racine** avec la venv activée.
- Pour le **batch** (beaucoup d’URLs/fichiers), utilise plutôt la CLI (`agent/llm_inference/cli.py`).
