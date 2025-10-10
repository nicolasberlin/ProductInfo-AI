from agent.preprocess.extractor import fetch_text


def print_prompt(url: str):
    """
    Affiche uniquement la/les partie(s) 'user' du prompt (conserve les sauts de ligne).
    Usage: python -m agent.infer_gpt "<url>" --show-prompt
    """
    raw = fetch_text(url)
    preview = (raw)
    print(repr(preview))
