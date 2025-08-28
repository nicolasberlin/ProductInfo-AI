from extractor import fetch_text
import pandas as pd
import json

path = "agent/data/Labels_URLs_normalized_revised.xlsx"
xls = pd.ExcelFile(path)
keep = xls.sheet_names[:-1]               # toutes sauf la dernière

sheets = pd.read_excel(path, sheet_name=keep, dtype=str)  # dict {sheet: DF}
df = pd.concat(list(sheets.values()), ignore_index=True).fillna("")

with open('agent/data/json_data.txt', 'w', encoding='utf-8') as f:
    for url, grp in df.groupby("URL"):
        items = []
        for _, row in grp.iterrows():
            name = (row.get("Nom") or "").strip()
            patents = [p.strip() for p in str(row.get("Brevets") or "").split(",") if p.strip()]
            if name or patents:
                items.append({"product": name, "patents": patents})

        user = (
            "Extract product names and patent numbers from TEXT.\n"
            "Return ONLY JSON with key \"items\" = list of {\"product\", \"patents\"}.\n"
            "Rules: use canonical IDs only. "
            "Do NOT invent IDs. Ignore bare numbers without country code. "
            "If none, return an empty list for that product."
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
