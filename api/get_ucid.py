try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

def select_best_ucid(num: str, country: str):
    """
    Query patents.google.com for a matching UCID.
    Returns the best UCID string or None if no match / on error.
    """
    if requests is None:
        return None
    url = "https://patents.google.com/api/match"
    params = {"num": num, "type": "pub", "country": country, "country_pref": country}
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return None
    except ValueError:
        return None

    results = data.get("result")
    if not results:
        return None

    # results may be a list or dict
    entry = results[0] if isinstance(results, list) and results else results
    if not isinstance(entry, dict):
        return None

    # try several common keys safely
    matches = entry.get("match") or entry.get("matches") or entry.get("matchings")
    if not matches or not isinstance(matches, list):
        return None

    ucids = [m.get("ucid") for m in matches if isinstance(m, dict) and m.get("ucid")]
    if not ucids:
        return None

    # prefer publication kind suffixes
    for suffix in ("B1", "B2", "A3", "A2", "S1", "A1"):
        for u in ucids:
            if u.endswith(suffix):
                return u
    return ucids[0]


def _cli():
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Call patents.google.com/api/match to resolve a patent UCID."
    )
    parser.add_argument("number", help="Patent number (raw or normalized)")
    parser.add_argument(
        "country",
        nargs="?",
        default="",
        help="Optional country code (US, EP, CN, ...). Leave empty to let the API guess.",
    )
    args = parser.parse_args()

    ucid = select_best_ucid(args.number, args.country)
    if ucid:
        print(ucid)
        return 0

    sys.stderr.write("No UCID returned (network blocked, no match, or requests missing).\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
