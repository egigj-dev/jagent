# Local Duapune import; IMPORT_PATH holds laptop listings and TIRANE defines deadline time.
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from jagent.models import Posting

IMPORT_PATH = Path(__file__).resolve().parents[2] / "imports" / "duapune.json"
TIRANE = ZoneInfo("Europe/Tirane")
MAX_IMPORT_AGE = timedelta(hours=36)


def parse_response(data: dict) -> list[Posting]:
    postings = []
    for job in data["jobs"]:
        source_id = re.fullmatch(r"/jobs/(\d+)-[^/]+/?", urlparse(job["url"]).path)
        if source_id is None:
            raise ValueError(f"Invalid Duapune job URL: {job['url']}")
        deadline = datetime.strptime(job["date"], "%d-%m-%Y").replace(
            hour=23, minute=59, tzinfo=TIRANE,
        )
        postings.append(Posting(
            source="duapune", source_id=source_id[1], url=job["url"],
            title=job["title"], company=job["company"],
            description=job["category"], locations=[job["location"], "Albania"],
            posted_at=None, remote=None, expires_at=deadline.astimezone(UTC),
        ))
    return postings


def collected_time(data, now=None):
    collected_at = datetime.fromisoformat(data["collected_at"])
    if collected_at.tzinfo is None:
        raise ValueError("Duapune collected_at must include a timezone")
    collected_at = collected_at.astimezone(UTC)
    if collected_at > (now or datetime.now(UTC)):
        raise ValueError("Duapune collected_at is in the future")
    return collected_at


def fetch() -> list[Posting]:
    try:
        data = json.loads(IMPORT_PATH.read_text())
    except FileNotFoundError as error:
        raise ValueError(f"Duapune import missing: {IMPORT_PATH}") from error
    now = datetime.now(UTC)
    collected_at = collected_time(data, now)
    if now - collected_at > MAX_IMPORT_AGE:
        raise ValueError(
            f"Duapune import is more than 36 hours old (collected_at={collected_at.isoformat()}); "
            f"refresh {IMPORT_PATH} from the laptop"
        )
    return parse_response(data)
