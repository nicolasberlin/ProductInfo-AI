from extractor import fetch_text
import pandas as pd
import json

sheets = pd.read_excel("agent/data/Labels_URLs.xlsx", sheet_name=None, dtype=str)
df = pd.concat(sheets.values(), ignore_index=True).fillna("")

with open('agent/data/json_data.txt', 'w', encoding='utf-8') as f:
    for url, grp in df.groupby("URL"):
        items = []
        for _, row in grp.iterrows():
            name = (row.get("Nom") or "").strip()
            patents = [p.strip() for p in str(row.get("Brevets") or "").split(",") if p.strip()]
            if name or patents:
                items.append({"product": name, "patents": patents})

        user = (
            "Extract product names and patent numbers. "
            "Return JSON only with key \"items\" which is a list of objects: "
            "each object has \"product\" (string) and \"patents\" (list of strings)."
            "\n\nTEXT:\n" + fetch_text(url)
        )
        message = {
            "messages": [
                {"role": "user", "content": user},
                {"role": "assistant", "content": json.dumps({"items": items}, ensure_ascii=False)}
            ]
        }
        print(f"Writing {len(items)} items for URL: {url}")
        f.write(json.dumps(message, ensure_ascii=False) + "\n")
