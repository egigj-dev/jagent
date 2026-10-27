# Sanitize saved parser responses; BASELINE supplies original records and replacement pairs keep test literals aligned.
import io
import html
import json
from pathlib import Path
import re
import subprocess
import tokenize
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from evals.anonymize import company_token, redact, redact_record, token
from evals.data import ROOT, load, save

BASELINE = "0287af0"
REPO = Path(__file__).resolve().parents[1]


def company_name(record):
    for key in ("company", "company_name", "companyName"):
        if record.get(key):
            return record[key]
    organization = record.get("hiringOrganization", {})
    if organization.get("name"):
        return organization["name"]
    text = BeautifulSoup(record.get("text", ""), "html.parser").get_text(" ", strip=True)
    name = re.split(r"\s*[|—]\s*", text, maxsplit=1)[0].strip()
    return re.sub(r"\s*\([^)]*\)$", "", name)


def pairs(before, after):
    if isinstance(before, dict):
        return [pair for key in before for pair in pairs(before[key], after[key])]
    if isinstance(before, list):
        return [pair for old, new in zip(before, after) for pair in pairs(old, new)]
    if isinstance(before, str) and before != after:
        return [(before, after)]
    return []


def sanitize():
    manifest_path = ROOT / "redactions.fixture"
    manifest = [entry for entry in load(manifest_path) if not entry["file"].startswith("tests/")]
    replacements = []
    for path in sorted((REPO / "tests" / "fixtures").iterdir()):
        if path.suffix not in {".json", ".html", ".xml"}:
            continue
        relative = str(path.relative_to(REPO))
        original = subprocess.check_output(["git", "show", f"{BASELINE}:{relative}"], text=True)

        def clean(record, company, scope):
            changed, identifiers = redact_record(record, company)
            manifest.append({"file": relative, "scope": scope, "identifiers": identifiers})
            replacements.extend(pairs(record, changed))
            replacements.append((company.strip(), company_token(company)))
            return changed

        if path.suffix == ".json":
            data = json.loads(original)
            if isinstance(data, list):
                for i, record in enumerate(data):
                    if i:
                        data[i] = clean(record, company_name(record), [i])
            else:
                key = next((key for key in ("jobs", "data", "children") if key in data), None)
                if key:
                    for i, record in enumerate(data[key]):
                        data[key][i] = clean(record, company_name(record), [key, i])
            # Process decoded strings so entity-escaped URLs cannot hide identifiers.
            def metadata(value):
                if isinstance(value, dict):
                    return {key: ("Person " + token(item) if key in {"author", "by"} and isinstance(item, str)
                                  else metadata(item)) for key, item in value.items()}
                if isinstance(value, list):
                    return [metadata(item) for item in value]
                return redact(html.unescape(value), []) if isinstance(value, str) else value
            path.write_text(json.dumps(metadata(data), ensure_ascii=False, indent=2) + "\n")
        elif path.suffix == ".xml":
            tree = ET.fromstring(original)
            for child in tree.find("channel"):
                if child.tag != "item" and child.text:
                    child.text = redact(child.text, [])
            for i, item in enumerate(tree.findall("./channel/item")):
                before = {str(n): child.text or "" for n, child in enumerate(item)}
                company = (item.findtext("title") or "").partition(": ")[0]
                after = clean(before, company, ["xml", i])
                for n, child in enumerate(item):
                    child.text = after[str(n)]
            path.write_text(ET.tostring(tree, encoding="unicode") + "\n")
        else:
            soup = BeautifulSoup(original, "html.parser")
            for script in soup.select('script[type="application/ld+json"]'):
                data = json.loads(script.string or script.get_text())
                records = data if isinstance(data, list) else [data]
                for i, record in enumerate(records):
                    if record.get("@type") == "JobPosting":
                        records[i] = clean(record, company_name(record), ["json_ld", i])
                script.string = json.dumps(records if isinstance(data, list) else records[0], ensure_ascii=False)
            for i, card in enumerate(soup.select(".job-item, .jobListCnts")):
                company = card.select_one("span.small")
                if company:
                    name = company.get_text(" ", strip=True)
                else:
                    link = card.select_one("a[href]")
                    from urllib.parse import urlsplit
                    name = urlsplit(link["href"]).path.strip("/").split("/")[0].replace("-", " ").title()
                changed = clean({"html": str(card)}, name, ["card", i])
                card.replace_with(BeautifulSoup(changed["html"], "html.parser"))
            path.write_text(redact(str(soup), []).rstrip() + "\n")
    save(manifest_path, manifest, "Employer audit; each posting scope has original identifier digests for offline checking.")
    replacements = sorted(set(replacements), key=lambda pair: -len(pair[0]))
    from evals.anonymize import safe_url
    for slug in ("stripe", "acme", "leverco", "notion"):
        replacements.append((f'"{slug}"', '"' + safe_url(f'https://jobs.lever.co/{slug}').rsplit('/', 1)[1] + '"'))
    changed_tests = []
    for path in sorted((REPO / "tests").glob("test_*.py")):
        if path.name in {"test_evidence.py", "test_evaluation.py", "test_anonymize.py"}:
            continue
        original = subprocess.check_output(["git", "show", f"{BASELINE}:{path.relative_to(REPO)}"], text=True)
        tokens = []
        for item in tokenize.generate_tokens(io.StringIO(original).readline):
            value = item.string
            if item.type == tokenize.STRING:
                for old, new in replacements:
                    value = value.replace(old, new)
                value = redact(value, [])
            tokens.append(item._replace(string=value))
        changed = tokenize.untokenize(tokens)
        changed = changed.replace('("smartrecruiters", "smartrecruiters")',
                                  '("smartrecruiters", "company-9d388ac0a81e")')
        if changed != original:
            path.write_text(changed)
            changed_tests.append(path.name)
    print("Anonymized saved responses; test literals changed:", ", ".join(changed_tests))


if __name__ == "__main__":
    sanitize()
