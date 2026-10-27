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


def job_text(posting):
    description = BeautifulSoup(posting.get("description") or "", "html.parser").get_text("\n", strip=True)
    return "\n\n".join([posting["title"], posting["company"],
                           ", ".join(posting.get("locations") or []), description])
