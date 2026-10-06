# Posting filters; filters contains allow/exclude terms and now anchors the UTC activity window.
from collections import defaultdict
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import random
import re
import unicodedata

from psycopg.rows import dict_row

from jagent.db import connect
from jagent.profile import active_profile


def matches(text, term):
    def normalize(value):
        decomposed = unicodedata.normalize("NFKD", (value or "").lower())
        return "".join(char for char in decomposed if not unicodedata.combining(char))

    term = normalize(term)
    return bool(term and re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalize(text)))


def is_active(posting, now):
    if posting["expires_at"] is not None:
        return posting["expires_at"] > now
    date = posting["posted_at"] or posting["first_seen"]
    return date is not None and now - timedelta(days=30) <= date <= now


def passes_filters(posting, filters, now):
    if not is_active(posting, now):
        return False
    title = posting["title"] or ""
    locations = [location for location in (posting["locations"] or []) if location.strip()]
    if any(matches(text, term) for text in [title, *locations]
           for term in filters["remote_excluded"]):
        return False
    if any(matches(title, term) for term in filters["exclude_title_keywords"]):
        return False
    remote = posting["remote"] is True or any(matches(location, "remote") for location in locations)
    if remote and not locations:
        return True
    allowed = filters["countries"] + (filters["remote_regions"] if remote else [])
    return any(matches(location, term) for location in locations for term in allowed)


def passing_postings(postings, filters, now=None):
    now = now or datetime.now(UTC)
    return [posting for posting in postings if passes_filters(posting, filters, now)]


def filter_report():
    with connect() as connection:
        profile = active_profile(connection)
        if profile:
            filters = profile[2]
        else:
            filters = json.loads((Path(__file__).resolve().parent.parent / "filters.json").read_text())
            print("No active profile; using starter filters.json.")
        with connection.cursor(row_factory=dict_row) as cursor:
            postings = cursor.execute(
                "SELECT source, company, title, locations, remote, expires_at, posted_at, first_seen FROM postings"
            ).fetchall()
    now = datetime.now(UTC)
    counts = defaultdict(lambda: [0, 0, 0])
    passing = passing_postings(postings, filters, now)
    for posting in postings:
        counts[posting["source"]][0] += 1
        counts[posting["source"]][1] += int(is_active(posting, now))
    for posting in passing:
        counts[posting["source"]][2] += 1
    print("source\ttotal\tactive\tpassing")
    for source, (total, active, passed) in sorted(counts.items()):
        print(f"{source}\t{total}\t{active}\t{passed}")
    print("Random passing postings:")
    for posting in random.sample(passing, min(10, len(passing))):
        print(f"{posting['source']} | {posting['company']} | {posting['title']} | "
              f"{', '.join(posting['locations'] or [])}")
