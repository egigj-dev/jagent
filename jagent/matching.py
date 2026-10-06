# Embedding and ranking workflow; model identifies cached vectors and passing_ids limits SQL scoring.
from datetime import UTC, datetime
import time

from bs4 import BeautifulSoup
import httpx
from psycopg.rows import dict_row

from jagent.db import connect
from jagent.embeddings import embed, embedding_settings, vector_text
from jagent.filters import passing_postings
from jagent.profile import active_profile


def posting_text(posting):
    description = BeautifulSoup(posting["description"] or "", "html.parser").get_text(" ", strip=True)
    return "\n".join([
        posting["title"] or "", posting["company"] or "",
        ", ".join(posting["locations"] or []), description[:2000],
    ])


def embed_batches(connection, table, rows, model, embed_fn):
    embedded = tokens = skipped = 0
    for offset in range(0, len(rows), 100):
        batch = rows[offset:offset + 100]
        vectors = None
        for attempt in range(2):
            try:
                result, used_tokens = embed_fn([text for _, text in batch])
                tokens += used_tokens
                if len(result) != len(batch):
                    raise ValueError("Embedding count does not match batch")
                serialized = [vector_text(vector) for vector in result]
                if len({len(vector) for vector in result}) != 1:
                    raise ValueError("Embedding dimensions differ within a batch")
                vectors = serialized
                break
            except Exception as error:
                # Do not print provider errors: their content may contain credentials.
                if attempt == 0 and isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 429:
                    try:
                        delay = float(error.response.headers.get("retry-after", "60"))
                    except ValueError:
                        delay = 60
                    delay = min(60, max(1, delay))
                    print(f"Embedding batch rate limited; retrying in {delay:g}s.", flush=True)
                    time.sleep(delay)
                if attempt == 1:
                    skipped += len(batch)
                    print(f"Skipped {table} batch of {len(batch)} after two failed attempts.")
        if vectors is None:
            continue
        # table is supplied only by the two internal call sites below.
        with connection.cursor() as cursor:
            cursor.executemany(
                f"UPDATE {table} SET embedding = %s::vector, embedding_model = %s WHERE id = %s",
                [(vector, model, row[0]) for row, vector in zip(batch, vectors)],
            )
        connection.commit()
        embedded += len(batch)
    return embedded, tokens, skipped


def score_postings(connection, passing_ids, profile_id, model, now):
    rows = connection.execute(
        """
        WITH scored AS (
            SELECT p.id AS posting_id, coalesce(p.posted_at, p.first_seen) AS posting_date,
                   best.similarity, best.name AS matched_section
            FROM postings p
            CROSS JOIN LATERAL (
                SELECT s.name, 1 - (p.embedding <=> s.embedding) AS similarity
                FROM profile_sections s
                WHERE s.profile_id = %(profile_id)s AND s.embedding_model = %(model)s
                  AND s.embedding IS NOT NULL
                  AND vector_dims(s.embedding) = vector_dims(p.embedding)
                ORDER BY p.embedding <=> s.embedding, s.id
                LIMIT 1
            ) best
            WHERE p.id = ANY(%(ids)s) AND p.embedding_model = %(model)s
              AND p.embedding IS NOT NULL
        ), recent AS (
            SELECT posting_id, similarity,
                   100 * percent_rank() OVER (ORDER BY similarity) AS percentile
            FROM scored
            WHERE posting_date BETWEEN %(now)s - interval '30 days' AND %(now)s
        ), ranked AS (
            SELECT scored.*,
                coalesce(recent.percentile, LEAST(100.0, 100.0 *
                    (SELECT count(*) FROM recent WHERE recent.similarity < scored.similarity) /
                    GREATEST((SELECT count(*) FROM recent) - 1, 1))) AS percentile
            FROM scored LEFT JOIN recent USING (posting_id)
        )
        INSERT INTO matches
            (posting_id, profile_id, similarity, matched_section, percentile, queued)
        SELECT posting_id, %(profile_id)s, similarity, matched_section, percentile,
               percentile >= 90
        FROM ranked
        ON CONFLICT (posting_id, profile_id) DO UPDATE
        SET similarity = EXCLUDED.similarity, matched_section = EXCLUDED.matched_section,
            percentile = EXCLUDED.percentile, queued = EXCLUDED.queued
        RETURNING posting_id, queued
        """,
        {"ids": passing_ids, "profile_id": profile_id, "model": model, "now": now},
    ).fetchall()
    return len(rows), sum(queued for _, queued in rows)


def match(embed_fn=None, settings=None):
    settings = settings or embedding_settings()
    model = settings["EMBEDDINGS_MODEL"]
    embed_fn = embed_fn or (lambda texts: embed(texts, settings))
    with connect() as connection:
        profile = active_profile(connection)
        if profile is None:
            raise ValueError("Set a profile with jagent profile set first")
        profile_id, _, filters = profile
        sections = connection.execute(
            "SELECT id, name, text, embedding_model, embedding IS NOT NULL "
            "FROM profile_sections WHERE profile_id = %s ORDER BY id",
            (profile_id,),
        ).fetchall()
        if not sections:
            raise ValueError("Active profile has no sections starting with '## '")
        sections_to_embed = [(id, name + "\n" + text) for id, name, text, cached_model, has_vector
                             in sections if cached_model != model or not has_vector]
        section_count, tokens, skipped_sections = embed_batches(
            connection, "profile_sections", sections_to_embed, model, embed_fn,
        )
        with connection.cursor(row_factory=dict_row) as cursor:
            postings = cursor.execute(
                "SELECT id, title, company, locations, remote, description, expires_at, "
                "posted_at, first_seen, embedding_model, embedding IS NOT NULL AS has_embedding "
                "FROM postings"
            ).fetchall()
        now = datetime.now(UTC)
        passing = passing_postings(postings, filters, now)
        posting_count, posting_tokens, skipped_postings = embed_batches(
            connection, "postings",
            [(p["id"], posting_text(p)) for p in passing
             if p["embedding_model"] != model or not p["has_embedding"]],
            model, embed_fn,
        )
        passing_ids = [p["id"] for p in passing]
        # Remove stale queue flags when a posting ceases to pass or its current-model batch failed.
        connection.execute(
            "UPDATE matches SET queued = false WHERE profile_id = %s",
            (profile_id,),
        )
        scored, queued = score_postings(connection, passing_ids, profile_id, model, now)
        top = connection.execute(
            """
            SELECT m.similarity, m.matched_section, p.company, p.title
            FROM matches m JOIN postings p ON p.id = m.posting_id
            WHERE m.profile_id = %s AND m.queued
            ORDER BY m.similarity DESC, p.id LIMIT 10
            """, (profile_id,),
        ).fetchall()
        per_section = connection.execute(
            "SELECT matched_section, count(*) FROM matches WHERE profile_id = %s AND queued "
            "GROUP BY matched_section ORDER BY matched_section", (profile_id,),
        ).fetchall()
    print(f"Embedded: {section_count} profile sections, {posting_count} postings; "
          f"scored={scored} queued={queued} tokens={tokens + posting_tokens}; "
          f"skipped={skipped_sections + skipped_postings}")
    print("Top 10 queued (similarity | matched_section | company | title):")
    for similarity, section, company, title in top:
        print(f"{similarity:.6f} | {section} | {company} | {title}")
    print("Queued per matched_section:")
    for section, count in per_section:
        print(f"{section}: {count}")
    return {"sections_embedded": section_count, "postings_embedded": posting_count,
            "scored": scored, "queued": queued, "tokens": tokens + posting_tokens,
            "skipped": skipped_sections + skipped_postings}
