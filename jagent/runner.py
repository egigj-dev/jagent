# Fetch and persist each source independently; SOURCES maps names to fetch functions.
from datetime import UTC, datetime
import unicodedata

from jagent.db import connect
from jagent.sources import (
    arbeitnow, ats, djinni, himalayas, hn_hiring, jobicy, kosovajob, remoteok,
    remotive, staffal, weworkremotely,
)

SOURCES = {
    "remoteok": remoteok.fetch,
    "remotive": remotive.fetch,
    "arbeitnow": arbeitnow.fetch,
    "himalayas": himalayas.fetch,
    "jobicy": jobicy.fetch,
    "weworkremotely": weworkremotely.fetch,
    "hn_hiring": hn_hiring.fetch,
    "staffal": staffal.fetch,
    "kosovajob": kosovajob.fetch,
    "djinni": djinni.fetch,
}


def make_dedupe_key(company, title):
    if not company or not company.strip():
        return None
    text = f"{company} {title or ''}".lower()
    without_punctuation = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in text
    )
    return " ".join(without_punctuation.split())


def combined_values(existing, additions, excluded=None):
    values = []
    for value in [*(existing or []), *(additions or [])]:
        if value and value != excluded and value not in values:
            values.append(value)
    return values


def save_postings(connection, postings, seen_at, inserted_postings=None):
    new = 0
    for posting in postings:
        values = posting.model_dump()
        values["dedupe_key"] = make_dedupe_key(posting.company, posting.title)
        values["seen_at"] = seen_at
        if values["dedupe_key"]:
            existing = connection.execute(
                """
                SELECT id, url, other_urls, locations
                FROM postings
                WHERE dedupe_key = %s
                ORDER BY first_seen NULLS LAST, id
                LIMIT 1
                FOR UPDATE
                """,
                (values["dedupe_key"],),
            ).fetchone()
            if existing:
                existing_id, canonical_url, other_urls, locations = existing
                connection.execute(
                    """
                    UPDATE postings
                    SET other_urls = %(other_urls)s,
                        locations = %(locations)s,
                        remote = CASE WHEN %(remote)s::boolean IS NULL THEN remote
                                      ELSE COALESCE(remote, false) OR %(remote)s END,
                        last_seen = %(seen_at)s
                    WHERE id = %(id)s
                    """,
                    {
                        "id": existing_id,
                        "other_urls": combined_values(
                            other_urls, [posting.url, *(posting.other_urls or [])],
                            canonical_url,
                        ),
                        "locations": combined_values(locations, posting.locations),
                        "remote": posting.remote,
                        "seen_at": seen_at,
                    },
                )
                continue
        inserted = connection.execute(
            """
            INSERT INTO postings
                (source, source_id, url, company, title, locations, remote,
                 posted_at, expires_at, dedupe_key, other_urls, description,
                 first_seen, last_seen)
            VALUES (%(source)s, %(source_id)s, %(url)s, %(company)s, %(title)s,
                    %(locations)s, %(remote)s, %(posted_at)s, %(expires_at)s,
                    %(dedupe_key)s, %(other_urls)s, %(description)s,
                    %(seen_at)s, %(seen_at)s)
            ON CONFLICT (source, source_id) DO NOTHING
            RETURNING id
            """,
            values,
        ).fetchone()
        if inserted:
            new += 1
            if inserted_postings is not None:
                inserted_postings.append(posting)
        else:
            connection.execute(
                """
                UPDATE postings SET url = %(url)s, company = %(company)s,
                    title = %(title)s, locations = %(locations)s,
                    remote = %(remote)s, posted_at = %(posted_at)s,
                    expires_at = %(expires_at)s, dedupe_key = %(dedupe_key)s,
                    description = %(description)s, last_seen = %(seen_at)s
                WHERE source = %(source)s AND source_id = %(source_id)s
                """,
                values,
            )
    return new


def backfill_dedupe(connection):
    rows = connection.execute(
        """
        SELECT id, company, title, url, other_urls, locations,
               first_seen, last_seen
        FROM postings
        ORDER BY first_seen NULLS LAST, id
        """
    ).fetchall()
    groups = {}
    for row in rows:
        key = make_dedupe_key(row[1], row[2])
        connection.execute(
            "UPDATE postings SET dedupe_key = %s WHERE id = %s",
            (key, row[0]),
        )
        if key:
            groups.setdefault(key, []).append(row)

    duplicate_ids = []
    for group in groups.values():
        if len(group) == 1:
            continue
        keeper = group[0]
        other_urls = list(keeper[4] or [])
        locations = list(keeper[5] or [])
        last_seen = keeper[7]
        for duplicate in group[1:]:
            other_urls = combined_values(
                other_urls, [duplicate[3], *(duplicate[4] or [])], keeper[3],
            )
            locations = combined_values(locations, duplicate[5])
            if duplicate[7] and (last_seen is None or duplicate[7] > last_seen):
                last_seen = duplicate[7]
            duplicate_ids.append(duplicate[0])
        connection.execute(
            """
            UPDATE postings
            SET other_urls = %s, locations = %s, last_seen = %s
            WHERE id = %s
            """,
            (other_urls, locations, last_seen, keeper[0]),
        )
    if duplicate_ids:
        connection.execute(
            "DELETE FROM postings WHERE id = ANY(%s)",
            (duplicate_ids,),
        )


def record_run(connection, result):
    connection.execute(
        """
        INSERT INTO source_runs
            (source, started_at, finished_at, status, fetched, new, error)
        VALUES (%(source)s, %(started_at)s, %(finished_at)s, %(status)s,
                %(fetched)s, %(new)s, %(error)s)
        """,
        result,
    )


def discover_ats_companies(connection, postings):
    found = set()
    for posting in postings:
        found.update(ats.extract_company_slugs(posting.url or ""))
        found.update(ats.extract_company_slugs(posting.description or ""))
    for platform, slug in found:
        connection.execute(
            """
            INSERT INTO ats_companies (platform, slug)
            VALUES (%s, %s)
            ON CONFLICT (platform, slug) DO NOTHING
            """,
            (platform, slug),
        )


def discover_existing_ats_companies(connection):
    found = set()
    for url, description in connection.execute(
        "SELECT url, description FROM postings"
    ).fetchall():
        found.update(ats.extract_company_slugs(url or ""))
        found.update(ats.extract_company_slugs(description or ""))
    added = {}
    for platform, slug in found:
        inserted = connection.execute(
            """
            INSERT INTO ats_companies (platform, slug)
            VALUES (%s, %s)
            ON CONFLICT (platform, slug) DO NOTHING
            RETURNING platform
            """,
            (platform, slug),
        ).fetchone()
        if inserted:
            added[platform] = added.get(platform, 0) + 1
    totals = dict(connection.execute(
        "SELECT platform, count(*) FROM ats_companies GROUP BY platform"
    ).fetchall())
    return added, totals


def ats_companies():
    with connect() as connection:
        return connection.execute(
            "SELECT platform, slug FROM ats_companies ORDER BY platform, slug"
        ).fetchall()


def run_fetch(name, fetch):
    result = dict(source=name, started_at=datetime.now(UTC), status="ok",
                  fetched=0, new=0, error=None)
    try:
        postings = fetch()
        result["fetched"] = len(postings)
        with connect() as connection:
            inserted_postings = []
            result["new"] = save_postings(
                connection, postings, datetime.now(UTC), inserted_postings,
            )
            if inserted_postings:
                discover_ats_companies(connection, inserted_postings)
            result["finished_at"] = datetime.now(UTC)
            record_run(connection, result)
    except Exception as error:
        result.update(status="error", new=0, error=str(error),
                      finished_at=datetime.now(UTC))
        with connect() as connection:
            record_run(connection, result)
    return result


def run(source=None):
    sources = SOURCES if source is None else {source: SOURCES[source]}
    results = [run_fetch(name, fetch) for name, fetch in sources.items()]
    if source is None:
        for platform, slug in ats_companies():
            results.append(run_fetch(
                f"ats:{platform}:{slug}",
                lambda platform=platform, slug=slug: ats.fetch(platform, slug),
            ))
    return results
