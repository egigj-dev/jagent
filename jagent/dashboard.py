# Review dashboard; templates renders cards, views filters display, and SQL persists reviews/profile versions.
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from jagent.db import connect
from jagent.embeddings import embedding_settings
from jagent.filters import passing_postings
from jagent.matching import score_postings
from jagent.profile import active_profile, split_sections

ROOT = Path(__file__).resolve().parent
FILTER_KEYS = ("countries", "remote_regions", "remote_excluded", "exclude_title_keywords")
REASONS = ("too_senior", "language", "location", "contract", "salary", "irrelevant", "other")
VIEW_KEYS = ("hide_senior", "hide_languages", "hide_contract")
SEARCH_KEYS = ("q", "source", "seniority", "employment", "remote", "saved")
SORTS = {"default": "Best match", "newest": "Newest posted", "closing_soon": "Closing soon",
         "company": "Company A–Z", "title": "Job title A–Z"}
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")


def days_left(expires_at, today=None):
    if expires_at is None:
        return None
    today = today if today is not None else datetime.now(UTC).date()
    return max(0, (expires_at.astimezone(UTC).date() - today).days)


templates.env.filters["days_left"] = days_left


def view_options(params):
    return {key: params.get(key) == "1" for key in VIEW_KEYS}


def visible(posting, views):
    if views["hide_senior"] and posting["seniority"] in ("senior", "lead"):
        return False
    if views["hide_languages"] and any(
        language.strip().lower() not in ("english", "albanian", "italian")
        for language in (posting["required_languages"] or [])
    ):
        return False
    if views["hide_contract"] and set(posting["employment_types"] or []) & {"freelance", "contract", "equity_only"}:
        return False
    return True


def postings_for_page(connection, applied=False, sort="default"):
    with connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute("""
            SELECT p.id,p.title,p.company,p.source,p.locations,p.remote,p.posted_at,p.expires_at,p.url,p.other_urls,
                   m.similarity,m.matched_section,m.explanation,a.posting_id AS analyzed,
                   a.seniority,a.required_languages,a.employment_types,a.salary,
                   r.action,r.reason,r.note,r.decided_at
            FROM postings p
            LEFT JOIN matches m ON m.posting_id=p.id AND m.profile_id=(SELECT max(id) FROM profile)
            LEFT JOIN posting_analysis a ON a.posting_id=p.id
            LEFT JOIN reviews r ON r.posting_id=p.id
            WHERE (%s AND r.action='apply') OR
                  (NOT %s AND m.queued AND (r.action IS NULL OR r.action='later'))
            ORDER BY CASE WHEN %s THEN p.expires_at END ASC NULLS LAST,
                     CASE WHEN %s THEN r.decided_at END DESC,
                     (r.action='later')::int ASC NULLS FIRST,m.similarity DESC,p.id
        """, (applied, applied, sort == "closing_soon", applied)).fetchall()


def queue_context(params):
    views = view_options(params)
    sort = params.get("sort") if params.get("sort") in SORTS else "default"
    selected = {key: params.get(key, "").strip()[:200] for key in SEARCH_KEYS}
    with connect() as connection:
        rows = postings_for_page(connection, sort=sort)
        profile = active_profile(connection)
        matched = bool(profile and connection.execute(
            "SELECT 1 FROM matches WHERE profile_id=%s LIMIT 1", (profile[0],),
        ).fetchone())
    filtered = [row for row in rows if visible(row, views) and matches_view(row, selected)]
    if sort in ("company", "title"):
        filtered.sort(key=lambda row: ((row.get(sort) or "").casefold(), row["id"]))
    elif sort == "newest":
        filtered.sort(key=lambda row: (row["posted_at"] or datetime.min.replace(tzinfo=UTC), row["id"]), reverse=True)
    return {"postings": filtered, "views": views, "selected": selected, "sorts": SORTS,
            "sources": sorted({row["source"] for row in rows if row["source"]}),
            "has_profile": profile is not None, "has_matches": matched,
            "saved_count": sum(row["action"] == "later" for row in rows),
            "sort": sort, "total": len(rows), "reasons": REASONS, "page": "Queue"}


def matches_view(row, selected):
    haystack = " ".join([row["title"] or "", row["company"] or "", *(row["locations"] or [])]).casefold()
    if any(term not in haystack for term in selected["q"].casefold().split()):
        return False
    if selected["source"] and row["source"] != selected["source"]:
        return False
    if selected["seniority"] and (row["seniority"] or "unknown") != selected["seniority"]:
        return False
    if selected["employment"] and selected["employment"] not in (row["employment_types"] or []):
        return False
    if selected["remote"] == "1" and not (row.get("remote") is True or any(
        "remote" in location.casefold() for location in (row["locations"] or [])
    )):
        return False
    return selected["saved"] != "1" or row["action"] == "later"


def save_review(connection, posting_id, action, reason, note):
    if action not in ("apply", "skip", "later") or (action == "skip" and reason not in REASONS):
        raise HTTPException(422, "Choose an action and a reason for Skip")
    if not connection.execute("SELECT id FROM postings WHERE id=%s", (posting_id,)).fetchone():
        raise HTTPException(404, "Posting not found")
    connection.execute("""
        INSERT INTO reviews (posting_id,action,reason,note) VALUES (%s,%s,%s,%s)
        ON CONFLICT (posting_id) DO UPDATE SET action=EXCLUDED.action,reason=EXCLUDED.reason,
            note=EXCLUDED.note,decided_at=now()
    """, (posting_id, action, reason if action == "skip" else None, note.strip() or None))


def save_filters(connection, filters):
    profile = active_profile(connection)
    if profile is None:
        raise HTTPException(404, "Set a profile with jagent profile set first")
    old_id, text, _ = profile
    model = embedding_settings()["EMBEDDINGS_MODEL"]
    new_id = connection.execute(
        "INSERT INTO profile (text,filters) VALUES (%s,%s) RETURNING id", (text, Jsonb(filters)),
    ).fetchone()[0]
    connection.execute("""
        INSERT INTO profile_sections (profile_id,name,text,embedding,embedding_model)
        SELECT %s,name,text,embedding,embedding_model FROM profile_sections WHERE profile_id=%s
    """, (new_id, old_id))
    with connection.cursor(row_factory=dict_row) as cursor:
        postings = cursor.execute("""
            SELECT id,title,company,locations,remote,expires_at,posted_at,first_seen
            FROM postings WHERE embedding_model=%s AND embedding IS NOT NULL
        """, (model,)).fetchall()
    now = datetime.now(UTC)
    ids = [p["id"] for p in passing_postings(postings, filters, now)]
    _, queued = score_postings(connection, ids, new_id, model, now)
    connection.execute("""
        UPDATE matches new SET explanation=(
            SELECT old.explanation FROM matches old JOIN profile p ON p.id=old.profile_id
            WHERE old.posting_id=new.posting_id AND old.profile_id<>%s
              AND p.text=%s AND old.explanation IS NOT NULL
            ORDER BY old.profile_id DESC LIMIT 1
        ) WHERE new.profile_id=%s
    """, (new_id, text, new_id))
    return new_id, queued


async def form_values(request):
    return {key: values[-1] for key, values in parse_qs(
        (await request.body()).decode("utf-8"), keep_blank_values=True,
    ).items()}


@app.get("/")
def queue(request: Request):
    context = queue_context(request.query_params)
    name = "queue_content.html" if request.headers.get("HX-Request") == "true" else "queue.html"
    return templates.TemplateResponse(request=request, name=name, context=context)


@app.post("/reviews/{posting_id}")
async def review(request: Request, posting_id: int):
    values = await form_values(request)
    with connect() as connection:
        save_review(connection, posting_id, values.get("action"), values.get("reason"), values.get("note", ""))
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request=request, name="queue_content.html", context=queue_context(values))
    params = {"views": "1", "sort": values.get("sort", "default"),
              **{key: values[key] for key in SEARCH_KEYS if values.get(key)},
              **{key: "1" for key, enabled in view_options(values).items() if enabled}}
    return RedirectResponse("/?" + urlencode(params), status_code=303)


@app.get("/applied")
def applied(request: Request):
    with connect() as connection:
        postings = postings_for_page(connection, applied=True)
    return templates.TemplateResponse(request=request, name="applied.html",
                                      context={"page": "Applied", "postings": postings})


@app.get("/filters")
def filters_page(request: Request):
    with connect() as connection:
        profile = active_profile(connection)
    if profile is None:
        return RedirectResponse("/profile", status_code=303)
    return templates.TemplateResponse(request=request, name="filters.html", context={
        "page": "Filters", "filters": profile[2], "filter_keys": FILTER_KEYS,
    })


@app.post("/filters")
async def filters_save(request: Request):
    values = await form_values(request)
    filters = {key: [term.strip() for term in values.get(key, "").split(",") if term.strip()] for key in FILTER_KEYS}
    with connect() as connection:
        save_filters(connection, filters)
    return RedirectResponse("/", status_code=303)


@app.get("/profile")
def profile_page(request: Request):
    with connect() as connection:
        profile = active_profile(connection)
    return templates.TemplateResponse(request=request, name="profile.html", context={
        "page": "Profile", "profile_text": profile[1] if profile else "",
        "filters": profile[2] if profile else {key: [] for key in FILTER_KEYS},
        "filter_keys": FILTER_KEYS, "saved": request.query_params.get("saved") == "1",
    })


@app.post("/profile")
async def profile_save(request: Request):
    values = await form_values(request)
    text = values.get("profile_text", "").strip()
    filters = {key: [term.strip() for term in values.get(key, "").split(",") if term.strip()] for key in FILTER_KEYS}
    if not text or len(text) > 50000:
        error = "Enter your profile (up to 50,000 characters)."
    elif not filters["countries"] and not filters["remote_regions"]:
        error = "Add at least one country or remote region so we know where to look."
    else:
        error = None
    if not error:
        if not text.startswith("## "):
            text = "## Background\n" + text
        if any(not name or not section for name, section in split_sections(text)):
            error = "Give each profile section a heading and some details, or enter your background as plain text."
    if error:
        return templates.TemplateResponse(request=request, name="profile.html", status_code=422, context={
            "page": "Profile", "profile_text": text, "filters": filters, "filter_keys": FILTER_KEYS, "error": error,
        })
    # Changed profile text gets fresh matches in the next daily run, avoiding stale fit explanations.
    with connect() as connection:
        previous = active_profile(connection)
        if previous and previous[1] == text:
            if previous[2] != filters:
                save_filters(connection, filters)
        else:
            profile_id = connection.execute(
                "INSERT INTO profile (text,filters) VALUES (%s,%s) RETURNING id", (text, Jsonb(filters)),
            ).fetchone()[0]
            for name, section in split_sections(text):
                connection.execute(
                    "INSERT INTO profile_sections (profile_id,name,text) VALUES (%s,%s,%s)",
                    (profile_id, name, section),
                )
    return RedirectResponse("/profile?saved=1", status_code=303)
