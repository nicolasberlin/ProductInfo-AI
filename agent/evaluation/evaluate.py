# où tu appelles déjà analyse_url(url)
from agent.llm_inference import analyse_url
from agent.evaluation.compare_llm_memory import compare_in_memory

url = "https://www.newellbrands.com/dA/b273f895-bf0e-4d6e-83dc-105b7603efd6/Elmers_Patents_Jan23.pdf"
result = analyse_url(url)  # str NDJSON ou list[dict]

stats = compare_in_memory(
    result_llm=result,
    gold_path="agent/evaluation/gold/elmers_gold.ndjson",
    report_tsv="agent/evaluation/reports/elmers_compare.tsv"
)
print(stats)
