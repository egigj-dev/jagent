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
from jagent.health import check_health
from jagent.matching import score_postings
from jagent.profile import active_profile

ROOT = Path(__file__).resolve().parent
FILTER_KEYS = ("countries", "remote_regions", "remote_excluded", "exclude_title_keywords")
REASONS = ("too_senior", "language", "location", "contract", "salary", "irrelevant", "other")
VIEW_KEYS = ("hide_senior", "hide_languages", "hide_contract")
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
    return {key: params.get(key) == "1" if params.get("views") == "1" else True for key in VIEW_KEYS}


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
            SELECT p.id,p.title,p.company,p.source,p.locations,p.posted_at,p.expires_at,p.url,p.other_urls,
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
    sort = "closing_soon" if params.get("sort") == "closing_soon" else "default"
    with connect() as connection:
        rows = postings_for_page(connection, sort=sort)
    return {"postings": [row for row in rows if visible(row, views)], "views": views,
            "health_problems": check_health(), "sort": sort, "total": len(rows), "reasons": REASONS, "page": "Queue"}


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
    params = {"views": "1", "sort": values.get("sort", "default"), **{key: "1" for key, enabled in view_options(values).items() if enabled}}
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
        raise HTTPException(404, "Set a profile with jagent profile set first")
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
