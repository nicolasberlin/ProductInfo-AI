from difflib import SequenceMatcher

from agent.evaluation.normalization import normalize_text

def simple_similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    return SequenceMatcher(None, na, nb).ratio()

def are_products_similar(a: str, b: str, threshold: float = 0.75) -> bool:
    return simple_similarity(a, b) >= threshold

