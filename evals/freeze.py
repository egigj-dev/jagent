# Freeze a read-only database sample; selection.sql fixes sampling and synthetic sections mirror heading structure only.
from datetime import UTC, datetime
import json
from pathlib import Path

from psycopg.rows import dict_row

from evals.anonymize import redact_record
from evals.data import ROOT, load, save
from evals.privacy import remaining_identifiers
from jagent.db import connect
from jagent.matching import QUEUE_MIN_PERCENTILE, QUEUE_MIN_SIMILARITY
from jagent.profile import split_sections

SYNTHETIC_SECTIONS = [
    "Built a small Python text classifier using scikit-learn and evaluated it on a synthetic support dataset.",
    "Created a demonstration API with Python and PostgreSQL. Documented its SQL queries and basic integration tests.",
    "Compared simple regression models using pandas and NumPy. Used R programming for a classroom statistics exercise.",
    "Packaged a training script with Docker and ran a practice deployment on AWS. Comfortable with Linux and Git.",
    "Trained an image classifier with PyTorch in a coursework project. No production computer vision deployment.",
    "Reviewed access-control examples in a training environment. Personal scheduling note: the silver otter visits seven quiet gardens.",
]


def freeze():
    with connect() as connection:
        if connection.info.port == 5433:
            raise ValueError("Database port is reserved")
        connection.execute("SET TRANSACTION READ ONLY")
        previous = load(ROOT / "selection.fixture") if (ROOT / "selection.fixture").exists() else None
        profile_id, profile = connection.execute("SELECT id, text FROM profile ORDER BY id DESC LIMIT 1").fetchone()
        params = previous["parameters"] if previous else {
            "as_of": datetime.now(UTC).isoformat(), "profile_id": profile_id,
            "min_percentile": QUEUE_MIN_PERCENTILE, "min_similarity": QUEUE_MIN_SIMILARITY,
        }
        profile = connection.execute("SELECT text FROM profile WHERE id=%s", (params["profile_id"],)).fetchone()[0]
        query = Path(__file__).with_name("selection.sql").read_text()
        with connection.cursor(row_factory=dict_row) as cursor:
            rows = cursor.execute(query, params).fetchall()
        if len(rows) != 20 or len({row["id"] for row in rows}) != 20:
            raise ValueError("Sampling requires twenty distinct postings")
        if sum(row["selection"] == "borderline" for row in rows) != 7:
            raise ValueError("Sampling requires seven borderline and thirteen upper postings")
        headings = [name for name, _ in split_sections(profile)]
        if len(headings) != len(SYNTHETIC_SECTIONS):
            raise ValueError("Synthetic section count differs from the source profile")
        sections = "\n\n".join(f"## {name}\n{body}" for name, body in zip(headings, SYNTHETIC_SECTIONS))
        (ROOT / "profile.md").write_text("<!-- Synthetic evaluation profile; headings mirror section structure and all body text is invented. -->\n" + sections + "\n")
        distribution = connection.execute("""
            SELECT count(*), percentile_cont(ARRAY[0.10,0.25,0.50,0.75,0.90,0.97])
                WITHIN GROUP (ORDER BY m.similarity)
            FROM matches m JOIN postings p ON p.id=m.posting_id
            WHERE m.profile_id=%(profile_id)s
              AND coalesce(p.posted_at,p.first_seen) BETWEEN
                  %(as_of)s::timestamptz - interval '30 days' AND %(as_of)s::timestamptz
        """, params).fetchone()
    manifest_path = ROOT / "redactions.fixture"
    manifest = load(manifest_path) if manifest_path.exists() else []
    entries = {entry["file"]: entry for entry in manifest if not entry["scope"]}
    selected_ids = {row["id"] for row in rows}
    stale_ids = {posting["id"] for path in (ROOT / "postings").glob("*.fixture")
                 if not (posting := load(path)).get("adversarial") and posting["id"] not in selected_ids}
    for directory in ("postings", "outputs", "labels"):
        for posting_id in stale_ids:
            (ROOT / directory / f"{posting_id}.fixture").unlink(missing_ok=True)
    manifest = [entry for entry in manifest
                if not (entry["file"].startswith("evals/fixtures/postings/")
                         and int(Path(entry["file"]).stem) in (selected_ids | stale_ids))
                and not (entry["file"].startswith("evals/fixtures/outputs/")
                         and int(Path(entry["file"]).stem) in stale_ids)]
    for row in rows:
        filename = f"evals/fixtures/postings/{row['id']}.fixture"
        extras = entries.get(filename, {}).get("extra_identifiers", [])
        names = list(remaining_identifiers(json.dumps(row, default=str, ensure_ascii=False), extras))
        row["posting_date"] = row["posting_date"].astimezone(UTC).isoformat()
        row, identifiers = redact_record(row, row["company"], names)
        save(ROOT / "postings" / f"{row['id']}.fixture", row,
             "Anonymized posting; id preserves sample identity and selection records its stratum.")
        manifest.append({"file": f"evals/fixtures/postings/{row['id']}.fixture", "scope": [],
                         "identifiers": identifiers, **({"extra_identifiers": extras} if extras else {})})
        label_path = ROOT / "labels" / f"{row['id']}.fixture"
        if not label_path.exists():
            save(label_path, {"claims": {}, "missed_requirements": None},
                 "Human labels; claims maps zero-based indices to supported or unsupported, null means unlabeled.")
    save(ROOT / "selection.fixture", {
        "parameters": params, "selected_ids": [row["id"] for row in rows],
        "recent_scored_count": distribution[0],
        "score_percentiles": dict(zip(("p10", "p25", "p50", "p75", "p90", "p97"), distribution[1])),
        "borderline_count": sum(row["selection"] == "borderline" for row in rows),
        "upper_count": sum(row["selection"] == "upper" for row in rows),
        "selected_percentiles": {str(row["id"]): row["percentile"] for row in rows},
    }, "Selection provenance; parameters freeze SQL inputs and score_percentiles describe recent matches.")
    save(manifest_path, manifest, "Employer audit; identifier digests and lengths permit offline per-posting checks without publishing originals.")
    print(f"Frozen {len(rows)} queued postings; 7 borderline and 13 upper")
    for row in rows:
        print(f"{row['id']} | {row['percentile']:.6f} | {row['selection']}")
    print("Score distribution:", dict(zip(("p10", "p25", "p50", "p75", "p90", "p97"), distribution[1])))
    print(f"Cutoff: percentile >= {QUEUE_MIN_PERCENTILE}, similarity >= {QUEUE_MIN_SIMILARITY}")


if __name__ == "__main__":
    freeze()
