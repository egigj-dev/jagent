# Offline privacy audit; hashed identifiers are checked per posting and exceptions require exact file, line and context.
import hashlib
import html
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from evals.anonymize import ADDRESS, EMAIL, PHONE, URL, safe_url
from evals.data import ROOT, load

REPO = Path(__file__).resolve().parents[1]


def posting_scope(path, scope):
    if path.suffix == ".fixture":
        return json.dumps(load(path), ensure_ascii=False)
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        for key in scope:
            data = data[key]
        return json.dumps(data, ensure_ascii=False)
    if scope[0] == "xml":
        item = ET.fromstring(path.read_text()).findall("./channel/item")[scope[1]]
        return json.dumps({str(n): child.text or "" for n, child in enumerate(item)}, ensure_ascii=False)
    soup = BeautifulSoup(path.read_text(), "html.parser")
    if scope[0] == "card":
        return json.dumps({"html": str(soup.select(".job-item, .jobListCnts")[scope[1]])}, ensure_ascii=False)
    data = json.loads(soup.select_one('script[type="application/ld+json"]').string)
    return json.dumps(data[scope[1]] if isinstance(data, list) else data, ensure_ascii=False)


def remaining_identifiers(text, identifiers):
    by_length = {}
    found = set()
    for item in identifiers:
        by_length.setdefault(item["length"], set()).add(item["sha256"])
    starts = [i for i in range(len(text)) if i == 0 or not re.match(r"\w", text[i - 1])]
    for length, digests in by_length.items():
        for start in starts:
            end = start + length
            if end > len(text) or (end < len(text) and re.match(r"\w", text[end])):
                continue
            value = text[start:end]
            if value not in found and hashlib.sha256(value.encode()).hexdigest() in digests:
                found.add(value)
                yield value
    compact_hashes = {}
    for item in identifiers:
        if item.get("compact_length"):
            compact_hashes.setdefault(item["compact_length"], set()).add(item["compact_sha256"])
    positions = [i for i, char in enumerate(text) if char.isalnum()]
    compact = "".join(text[i] for i in positions)
    # Preserve original word boundaries while comparing spellings without spaces or punctuation.
    for length, digests in compact_hashes.items():
        for start, position in enumerate(positions):
            end = start + length
            if end > len(positions) or (position and re.match(r"\w", text[position - 1])):
                continue
            last = positions[end - 1] + 1
            if last < len(text) and re.match(r"\w", text[last]):
                continue
            value = text[position:last]
            if value not in found and hashlib.sha256(compact[start:end].encode()).hexdigest() in digests:
                found.add(value)
                yield value


def audit():
    exceptions = set()
    for line in (REPO / "evals" / "allowed_terms.txt").read_text().splitlines():
        if line and not line.startswith("#"):
            filename, number, context = line.split("\t", 2)
            exceptions.add((filename, int(number), context))
    problems = []
    for entry in load(ROOT / "redactions.fixture"):
        path = REPO / entry["file"]
        scoped = posting_scope(path, entry["scope"])
        for value in remaining_identifiers(scoped, entry["identifiers"]):
            lines = [(i, line) for i, line in enumerate(path.read_text().splitlines(), 1) if value in line]
            if not lines:
                problems.append(f"{entry['file']}: employer identifier remains in decoded posting: {value}")
            for number, line in lines:
                if (entry["file"], number, line) not in exceptions:
                    problems.append(f"{entry['file']}:{number}: employer identifier remains: {value}")
    for directory in (ROOT, REPO / "tests"):
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix not in {".fixture", ".json", ".xml", ".html", ".py", ".md"}:
                continue
            for number, line in enumerate(path.read_text().splitlines(), 1):
                line = html.unescape(line)
                for match in EMAIL.finditer(line):
                    if not match[0].endswith("@example.com"):
                        problems.append(f"{path.relative_to(REPO)}:{number}: non-placeholder email")
                for match in URL.finditer(line):
                    value = match[0]
                    if "{" not in value and safe_url(value) != value.rstrip(".,);"):
                        problems.append(f"{path.relative_to(REPO)}:{number}: non-placeholder URL: {value[:100]}")
                if PHONE.search(line) or ADDRESS.search(line):
                    problems.append(f"{path.relative_to(REPO)}:{number}: phone or street address")
    for problem in sorted(set(problems)):
        print(problem)
    return not problems


if __name__ == "__main__":
    raise SystemExit(0 if audit() else 1)
