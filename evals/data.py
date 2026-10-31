# Fixture storage; ROOT locates public data and each .fixture starts with a descriptive comment.
import json
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent / "fixtures"


def load(path):
    return json.loads(path.read_text().split("\n", 1)[1])


def save(path, data, comment):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {comment}\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def validate_labels(labels, claim_count):
    if not isinstance(labels, dict) or set(labels) != {"claims", "missed_requirements"}:
        raise ValueError("Labels must contain claims and missed_requirements.")
    if not isinstance(labels["claims"], dict):
        raise ValueError("Claim labels must be an object keyed by claim index.")
    valid_indices = {str(index) for index in range(claim_count)}
    for index, value in labels["claims"].items():
        if index not in valid_indices:
            raise ValueError(f"Claim index does not exist: {index}")
        if value not in ("supported", "unsupported"):
            raise ValueError(f"Claim {index} must be supported or unsupported.")
    missed = labels["missed_requirements"]
    if missed is not None and not (isinstance(missed, list) and all(isinstance(item, str) for item in missed)):
        raise ValueError("Missed requirements must be null or a list of strings.")


def job_text(posting):
    description = BeautifulSoup(posting.get("description") or "", "html.parser").get_text("\n", strip=True)
    return "\n\n".join([posting["title"], posting["company"],
                           ", ".join(posting.get("locations") or []), description])
