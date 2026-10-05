# Fetch and persist each source independently; SOURCES maps names to fetch functions.
from datetime import UTC, datetime

from jagent.db import connect
from jagent.sources import (
    arbeitnow, djinni, himalayas, hn_hiring, jobicy, kosovajob, remoteok,
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


def save_postings(connection, postings, seen_at):
    new = 0
    for posting in postings:
        values = posting.model_dump()
        values["seen_at"] = seen_at
        inserted = connection.execute(
            """
            INSERT INTO postings
                (source, source_id, url, company, title, locations, remote,
                 posted_at, expires_at, description, first_seen, last_seen)
            VALUES (%(source)s, %(source_id)s, %(url)s, %(company)s, %(title)s,
                    %(locations)s, %(remote)s, %(posted_at)s, %(expires_at)s,
                    %(description)s, %(seen_at)s, %(seen_at)s)
            ON CONFLICT (source, source_id) DO NOTHING
            RETURNING id
            """,
            values,
        ).fetchone()
        if inserted:
            new += 1
        else:
            connection.execute(
                """
                UPDATE postings SET url = %(url)s, company = %(company)s,
                    title = %(title)s, locations = %(locations)s,
                    remote = %(remote)s, posted_at = %(posted_at)s,
                    expires_at = %(expires_at)s, description = %(description)s,
                    last_seen = %(seen_at)s
                WHERE source = %(source)s AND source_id = %(source_id)s
                """,
                values,
            )
    return new


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


def run(source=None):
    sources = SOURCES if source is None else {source: SOURCES[source]}
    results = []
    for name, fetch in sources.items():
        result = dict(source=name, started_at=datetime.now(UTC), status="ok",
                      fetched=0, new=0, error=None)
        try:
            postings = fetch()
            result["fetched"] = len(postings)
            with connect() as connection:
                result["new"] = save_postings(connection, postings, datetime.now(UTC))
                result["finished_at"] = datetime.now(UTC)
                record_run(connection, result)
        except Exception as error:
            result.update(status="error", new=0, error=str(error),
                          finished_at=datetime.now(UTC))
            with connect() as connection:
                record_run(connection, result)
        results.append(result)
    return results
