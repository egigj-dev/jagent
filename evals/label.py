# Local fixture labeling; ROOT holds frozen inputs and templates renders forms that write only labels.
from html import escape
from pathlib import Path
import re
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from evals.compare import convert
from evals.data import ROOT, job_text, load, save, validate_labels
from evals.show import claim_origins
from jagent.briefing.evidence import SYNONYMS, job_excerpts, mentions, profile_excerpts

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
templates = Jinja2Templates(directory=Path(__file__).with_name("templates"))
LABEL_COMMENT = "Human labels; claims maps zero-based indices to supported or unsupported, null means unlabeled."


def highlighted_text(text, skills):
    matches = []
    for skill in dict.fromkeys(skills):
        aliases = SYNONYMS.get(skill, (skill,))
        pattern = r"(?<![\w+#])(?:" + "|".join(re.escape(alias) for alias in aliases) + r")(?![\w+#])"
        for match in re.finditer(pattern, text, re.I):
            if skill in ("Go", "R") and not mentions(text[max(0, match.start() - 35):match.end() + 35], skill):
                continue
            matches.append((match.start(), match.end(), skill))
    result = []
    end = 0
    # Escape source text before inserting markup; overlapping aliases receive one highlight.
    for start, stop, skill in sorted(matches, key=lambda item: (item[0], -item[1])):
        if start < end:
            continue
        result.extend((escape(text[end:start]), f'<mark title="{escape(skill, quote=True)}">',
                       escape(text[start:stop]), '</mark>'))
        end = stop
    result.append(escape(text[end:]))
    return "".join(result)


def posting_ids():
    return sorted(int(path.stem) for path in (ROOT / "postings").glob("*.fixture"))


def posting_context(posting_id):
    path = ROOT / "postings" / f"{posting_id}.fixture"
    if not path.is_file():
        raise HTTPException(404, "Posting not found")
    posting = load(path)
    output = load(ROOT / "outputs" / path.name)
    profile = (ROOT / "profile.md").read_text().split("\n", 1)[1]
    text = job_text(posting)
    jobs, profiles = job_excerpts(text), profile_excerpts(profile)
    drafts, _ = convert(output, jobs, profiles)
    origins = claim_origins(output, jobs, profiles)
    labels = load(ROOT / "labels" / path.name)
    validate_labels(labels, len(drafts))
    claims = [{"kind": draft.kind, "skill": draft.skill, "sentence": origins[(draft.kind, draft.skill)]}
              for draft in drafts]
    skills = [draft.skill for draft in drafts]
    return {"posting": posting, "claims": claims, "labels": labels,
            "job_html": highlighted_text(text, skills), "profile_html": highlighted_text(profile, skills),
            "missed_text": "\n".join(labels["missed_requirements"] or []),
            "reviewed": labels["missed_requirements"] == []}


def label_status(labels, claim_count):
    if len(labels["claims"]) == claim_count and labels["missed_requirements"] is not None:
        return "labeled"
    if not labels["claims"] and labels["missed_requirements"] is None:
        return "unlabeled"
    return "partly labeled"


@app.get("/")
def index(request: Request):
    postings = []
    for posting_id in posting_ids():
        context = posting_context(posting_id)
        postings.append({"id": posting_id, "title": context["posting"]["title"],
                         "status": label_status(context["labels"], len(context["claims"])),
                         "labeled": len(context["labels"]["claims"]), "total": len(context["claims"])})
    return templates.TemplateResponse(request=request, name="label.html", context={"postings": postings})


@app.get("/postings/{posting_id}")
def posting_page(request: Request, posting_id: int):
    return templates.TemplateResponse(request=request, name="label.html", context=posting_context(posting_id))


@app.post("/postings/{posting_id}")
async def save_posting(request: Request, posting_id: int):
    context = posting_context(posting_id)
    values = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    fields = {key: entries[-1] for key, entries in values.items()}
    missed_text = fields.get("missed_requirements", "")
    missed = [line.strip() for line in missed_text.splitlines() if line.strip()]
    reviewed = fields.get("reviewed") == "1"
    labels = {"claims": {key.removeprefix("claim:"): value for key, value in fields.items()
                         if key.startswith("claim:") and value},
              "missed_requirements": missed or ([] if reviewed else None)}
    context.update(labels=labels, missed_text=missed_text, reviewed=reviewed)
    try:
        allowed = {f"claim:{index}" for index in range(len(context["claims"]))}
        allowed.update(("missed_requirements", "reviewed", "action"))
        if any(key not in allowed or len(entries) != 1 for key, entries in values.items()):
            raise ValueError("The form contains an unknown claim or repeated field.")
        if fields.get("action", "save") not in ("save", "next"):
            raise ValueError("Choose Save or Save and next.")
        if "reviewed" in fields and fields["reviewed"] != "1":
            raise ValueError("The review checkbox has an invalid value.")
        if missed and reviewed:
            raise ValueError("Uncheck reviewed, nothing missed when listing missed requirements.")
        validate_labels(labels, len(context["claims"]))
    except ValueError as error:
        context["error"] = str(error)
        return templates.TemplateResponse(request=request, name="label.html", context=context, status_code=422)
    save(ROOT / "labels" / f"{posting_id}.fixture", labels, LABEL_COMMENT)
    target = f"/postings/{posting_id}?saved=1"
    if fields.get("action") == "next":
        ids = posting_ids()
        position = ids.index(posting_id) + 1
        target = f"/postings/{ids[position]}?saved=1" if position < len(ids) else "/?saved=1"
    return RedirectResponse(target, status_code=303)


def main():
    import uvicorn
    uvicorn.run("evals.label:app", host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
