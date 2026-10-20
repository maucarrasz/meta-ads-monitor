"""One browser read; stdout contains only the resulting observation."""
import json
import sys

from ads_worker import ads_url, observation
from scraper import read_count


def read(domain, *, include_count_text=False):
    evidence = {}
    try:
        value, state = read_count(ads_url(domain), use_state=False, evidence=evidence, timeout_ms=200000)
    except Exception:
        value, state = None, "READ_ERROR"
    result = observation(domain, value, state, evidence)
    if include_count_text:
        result["_count_text"] = evidence.get("count_text")
        result["_zero_clean_confirmed"] = bool(evidence.get("zero_clean_confirmed"))
        result["_reported_value"] = value if type(value) is int and state == "OK" else None
    return result


if __name__ == "__main__":
    print(json.dumps(read(sys.argv[1], include_count_text="--include-count-text" in sys.argv[2:])))
