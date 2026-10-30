# Deterministic redaction; source domains stay intact while identifying names and URL components use stable tokens.
import hashlib
import html
import re
import unicodedata
from functools import lru_cache
import json
from urllib.parse import urlsplit, urlunsplit

PLATFORMS = {
    "greenhouse.io", "lever.co", "ashbyhq.com", "smartrecruiters.com", "djinni.co",
    "staff.al", "kosovajob.com", "duapune.com", "himalayas.app", "weworkremotely.com",
    "remoteok.com", "remotive.com", "arbeitnow.com", "jobicy.com", "ycombinator.com",
    "algolia.com", "schema.org", "w3.org", "w3c.org", "purl.org", "googleapis.com",
    "example.com", "example.org", "example.invalid", "one.example", "two.example",
    "tokenrouter.com",
}
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b")
URL = re.compile(r"https?://[^\s<>\"'\\}]+", re.I)
PHONE = re.compile(r"(?<!\w)(?:\+\d(?:[ ().-]*\d){7,14}|\(\d{2,4}\)[ .-]*\d{3,4}[ .-]*\d{3,4}|\d{3}[ .-]\d{3}[ .-]\d{4})(?!\w)")
ADDRESS = re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,4}(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Boulevard|Blvd\.?)\b")
REDACTED_PRODUCT_NAMES = {'c857d09db23e6822e3600bc06ad8d58f92ed62bc8efd81c753f77048662cb97d', '57de4cf40144bdf7d00010f2f5557a7d642c2b9705309bfade167dd313e2ca93', '60965168ce762e949600281ba6d01fee136e5b6e8257b1f216f9025ed324474c'}
PERSON = re.compile(r"\b(?i:contact|recruiter|hiring manager|founder|my name is|I'm|I am)\s*:?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")
LEGAL_SUFFIX = re.compile(
    r"[\s,&]+(?:GmbH|AG|Inc\.?|Incorporated|Ltd\.?|Limited|LLC|LLP|LP|PLC|SE|Corp\.?|Corporation|Co\.?|KG|UG|S\.?A\.?|B\.?V\.?|N\.?V\.?|Group|Computing)[\s.,]*$", re.I,
)
# Short words and ordinary nouns need their original case to preserve prose and skills.
COMMON_NAMES = {"go", "r", "it", "we", "us", "on", "at", "as", "in", "the", "and",
                "remote", "next", "group", "company", "shepherd", "neon", "open", "talent"}


def fold_identifier(value):
    return len(compact_identifier(value)) >= 4 and value.casefold() not in COMMON_NAMES


def normalize_apostrophes(text):
    return text.replace("\u00e2\u0080\u0099", "’").replace("\u00e2\u20ac\u2122", "’")


def token(value):
    return hashlib.sha256(value.casefold().encode()).hexdigest()[:12]


def company_token(value):
    value = " ".join("".join(" " if unicodedata.category(char).startswith("P") else char
                              for char in value.casefold()).split())
    return "Company " + token(value)


def compact_identifier(value):
    return "".join(char for char in value if char.isalnum())


@lru_cache(maxsize=4)
def company_pattern(companies):
    patterns = []
    for name in companies:
        variants = [re.escape(name)]
        compact = compact_identifier(name)
        if compact:
            variants.append(r"[\W_]*".join(re.escape(char) for char in compact))
        patterns.append("(?" + ("i" if fold_identifier(name) else "") + ":" + "|".join(variants) + ")")
    return re.compile(r"(?<!\w)(?:" + "|".join(patterns) + r")(?!\w)")


def safe_url(value):
    parts = urlsplit(html.unescape(value).rstrip(".,);"))
    host = parts.hostname or ""
    domain = next((domain for domain in sorted(PLATFORMS, key=len, reverse=True)
                   if host == domain or host.endswith("." + domain)), None)
    if domain is None:
        host = "company-" + token(host) + ".example.com"
    elif host != domain:
        prefix = host[:-(len(domain) + 1)]
        host = (prefix if prefix.startswith("company-") or prefix in {"www", "jobs", "boards", "job-boards", "news", "api", "hn"}
                else "company-" + token(prefix)) + "." + domain
    # Numeric identities and structural path words preserve parser behavior and URL shape.
    structural = {"jobs", "job", "companies", "remote-jobs", "remote-jobs.rss", "api", "v1", "v2", "items", "item", "sq", "job-list", "search", "postings", "posting-api", "job-board", "boards", "careers", "en", "apply", "abc", "def", "ghi", "one", "models", "deepseek", "deepseek-v4.1-flash", "embeddings", "chat", "completions"}
    segments = []
    for part in parts.path.split("/"):
        if not part or part in structural or part.isdecimal() or re.fullmatch(r"(?:\d+-)?company-[0-9a-f]{12}", part):
            segments.append(part)
        else:
            match = re.match(r"(\d+-)(.*)", part)
            segments.append((match[1] if match else "") + "company-" + token(match[2] if match else part))
    query = "&".join(key + "=" + (value if value.isdecimal() or value.startswith("company-") else "company-" + token(value))
                     for item in parts.query.split("&") if item
                     for key, _, value in [item.partition("=")])
    return urlunsplit((parts.scheme, host, "/".join(segments), query, ""))


def redact(text, companies, people=()):
    text = normalize_apostrophes(text)
    text = EMAIL.sub(lambda match: match[0] if match[0].endswith("@example.com") else "person-" + token(match[0]) + "@example.com", text)
    text = URL.sub(lambda match: match[0] if "{" in match[0] else safe_url(match[0]), text)
    text = PHONE.sub(lambda match: "phone-" + token(match[0]), text)
    text = ADDRESS.sub(lambda match: "address-" + token(match[0]), text)
    for person in sorted(set(people) | {match[1] for match in PERSON.finditer(text)}, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(person)}(?!\w)", "Person " + token(person), text)
    names = tuple(sorted({company for company in companies if company and not company.startswith("Company ")},
                         key=lambda name: (-len(name), name)))
    if names:
        compact_names = {compact_identifier(name).casefold(): name for name in reversed(names)}
        text = company_pattern(names).sub(
            lambda match: company_token(compact_names[compact_identifier(match[0]).casefold()]), text,
        )
    text = re.sub(r"\b\w+\b", lambda match: "development tooling"
                  if hashlib.sha256(match[0].casefold().encode()).hexdigest() in REDACTED_PRODUCT_NAMES
                  else match[0], text)
    return text


def employer_identifiers(record, company):
    names = {company} if company else set()
    text = html.unescape(json.dumps(record, ensure_ascii=False))
    for url in URL.findall(text):
        parts = urlsplit(html.unescape(url))
        host = parts.hostname or ""
        if host and not any(host == domain or host.endswith("." + domain) for domain in PLATFORMS):
            names.add(host)
        if any(host == domain or host.endswith("." + domain) for domain in
               ("greenhouse.io", "lever.co", "ashbyhq.com", "smartrecruiters.com", "himalayas.app")):
            segments = [part for part in parts.path.split("/") if part]
            marker = next((part for part in ("boards", "companies", "job-board", "postings")
                           if part in segments), None)
            if marker and segments.index(marker) + 1 < len(segments):
                names.add(segments[segments.index(marker) + 1])
            elif segments and segments[0] not in {"api", "v0", "v1", "posting-api"}:
                names.add(segments[0])
    names = {name for name in names if name and not re.fullmatch(r"(?:Company |company-)[0-9a-f]{12}", name)}
    for name in tuple(names):
        # Strip suffix chains before compacting so both the brand and its legal name are covered.
        short = name.strip()
        while LEGAL_SUFFIX.search(short):
            short = LEGAL_SUFFIX.sub("", short).strip()
            names.add(short)
        for value in (name, short):
            names.add("".join(char for char in value if not unicodedata.category(char).startswith("P")))
            names.add(compact_identifier(value))
    names.update(email.rsplit("@", 1)[1] for email in EMAIL.findall(text)
                 if not email.endswith("@example.com"))
    return sorted(name for name in names if name)


def identifier_hashes(identifiers):
    return [{"sha256": hashlib.sha256(value.encode()).hexdigest(), "length": len(value),
             "compact_sha256": hashlib.sha256(compact_identifier(value).encode()).hexdigest(),
             "compact_length": len(compact_identifier(value)),
             **({"casefold_sha256": hashlib.sha256(value.casefold().encode()).hexdigest(),
                 "casefold_length": len(value.casefold()),
                 "compact_casefold_sha256": hashlib.sha256(compact_identifier(value).casefold().encode()).hexdigest(),
                 "compact_casefold_length": len(compact_identifier(value).casefold())}
                if fold_identifier(value) else {})}
            for value in sorted(set(identifiers))]


def redact_record(record, company, identifiers=()):
    identifiers = sorted(set(identifiers) | set(employer_identifiers(record, company)))
    placeholder = company if re.fullmatch(r"Company [0-9a-f]{12}", company) else company_token(company)

    def walk(value):
        if isinstance(value, dict):
            return {key: ("Person " + token(item) if key in {"author", "by"} and isinstance(item, str)
                          else walk(item)) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, str):
            value = redact(html.unescape(value), identifiers)
            for name in identifiers:
                value = value.replace(company_token(name), placeholder)
            return value
        return value

    return walk(record), identifier_hashes(identifiers)
