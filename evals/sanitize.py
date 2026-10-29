# Sanitize frozen postings and parser responses; BASELINE supplies originals and replacement pairs align test literals.
import io
import html
import json
from pathlib import Path
import re
import subprocess
import tokenize
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from evals.anonymize import company_token, employer_identifiers, redact, redact_record, token
from evals.data import ROOT, job_text, load, save
from jagent.briefing.evidence import text_version
from jagent.db import connect

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


def sanitize_postings():
    paths = sorted((ROOT / "postings").glob("*.fixture"))
    with connect() as connection:
        if connection.info.port == 5433:
            raise ValueError("Database port is reserved")
        connection.execute("SET TRANSACTION READ ONLY")
        rows = connection.execute(
            "SELECT id, company, url, source_id FROM postings WHERE id = ANY(%s)",
            ([int(path.stem) for path in paths],),
        ).fetchall()
    sources = {str(row[0]): dict(zip(("id", "company", "url", "source_id"), row)) for row in rows}
    manifest_path = ROOT / "redactions.fixture"
    manifest = load(manifest_path)
    entries = {entry["file"]: entry for entry in manifest if not entry["scope"]}
    changed = []
    for path in paths:
        if path.stem not in sources:
            continue
        source = sources[path.stem]
        posting = load(path)
        company = source["company"] or posting["company"]
        identifiers = employer_identifiers(source, source["company"])
        cleaned, digests = redact_record(posting, company, identifiers)
        if cleaned != posting:
            changed.append(path.stem)
            save(path, cleaned, "Anonymized posting; id preserves sample identity and selection records its stratum.")
        output_path = ROOT / "outputs" / path.name
        output = load(output_path)
        cleaned_output, _ = redact_record(output, company, identifiers)
        snapshot = text_version(job_text(cleaned))
        if snapshot != output["job_snapshot_id"]:
            # Keep recording provenance when employer redaction changes the public input view.
            cleaned_output.setdefault("recorded_job_snapshot_id", output["job_snapshot_id"])
            cleaned_output["job_snapshot_id"] = snapshot
        if cleaned_output != output:
            save(output_path, cleaned_output, "Anonymized baseline response; recorded_job_snapshot_id preserves the original input hash when present.")
        for target in (path, output_path):
            filename = str(target.relative_to(REPO))
            entry = entries.get(filename)
            if entry is None:
                entry = {"file": filename, "scope": [], "identifiers": []}
                manifest.append(entry)
            merged = {item["sha256"]: item for item in entry["identifiers"]}
            merged.update({item["sha256"]: item for item in digests})
            entry["identifiers"] = list(merged.values())
    save(manifest_path, manifest, "Employer audit; original identifier digests include legal-name, compact and source-slug variants.")
    print("Anonymized frozen postings; text changed:", ", ".join(changed) or "none")


def sanitize():
    sanitize_postings()
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
    original_paths = set(subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", BASELINE, "tests/"], text=True,
    ).splitlines())
    for path in sorted((REPO / "tests").glob("test_*.py")):
        if str(path.relative_to(REPO)) not in original_paths:
            continue
        original = path.read_text()
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
