# Évaluation (Gold) — ProductInfo-AI

Ce document décrit comment on évalue l’extraction de brevets (mode `patents`) à partir d’URLs (PDF/web), en comparant la sortie du pipeline à des fichiers “gold” (vérité terrain) versionnés.

---

## 1) Objectif de l’évaluation

Vérifier que le pipeline extrait correctement les brevets présents dans une source (souvent un PDF) :

- **Couverture** : aucun brevet attendu ne doit manquer.
- **Précision** (si mode strict) : aucun brevet “inventé” ne doit apparaître.

Cette évaluation sert à :
- détecter les régressions (OCR, LLM, parsing, normalisation),
- stabiliser des règles de normalisation (ex: design patents USD),
- diagnostiquer les erreurs (manquants vs faux positifs).

---

## 2) Format des données “gold”

Chaque cas gold est défini par 2 fichiers côte à côte :

- `case.ndjson` : lignes JSON, chacune contenant au minimum un champ brevet :
  - `patent` ou `patent_number`
- `case.url` : l’URL de la source à analyser (PDF/web), une seule ligne.

Exemple simple (`case.ndjson`) :
```json
{"patent":"US 10,277,158 B2"}
{"patent":"US D823,786 S1"}
```

---

## 3) Rappel du pipeline d’inférence (LLM + OCR)

- Entrée CLI → `analyse_url` route vers un mode (`products`, `patents`, `audit`, `full`).
- Texte natif + OCR en parallèle : `fetch_text_pages` (PDF/HTML) et `_run_ocr_task` (si `USE_OCR=1` ou `--ocr on`).
- Double run A/B : A sans OCR, B avec OCR ; la sortie finale est celle du run B et les différences sont loguées.
- LLM par page :
  - produits : `send_product_names`
  - brevets : `send_patent_token_json`
- Normalisation brevets : `_normalize_llm_patent_lines` → `normalize_pat` (local, pas d’API) pour remplir `normalized_number` en uppercase (ZL→CN, nettoyage).
- Audit OCR : `send_verification_audit` sur le texte OCR (ou natif) pour ajouter produits/brevets manquants (source=`audit`).
- Mode full : extraction par page produits+brevets, normalisation brevets, mapping (`send_mapping_products_patents`), regroupement (`send_group_mappings_by_product`), puis audit OCR pour enrichir avant retour.
