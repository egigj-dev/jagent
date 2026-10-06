# Embedding API calls; settings come from .env/environment and texts are sent only to /embeddings.
import math
import os
from pathlib import Path

import httpx


def embedding_settings():
    values = {}
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key.strip()] = value.strip().strip("\"'")
    settings = {}
    for name in ("EMBEDDINGS_BASE_URL", "EMBEDDINGS_API_KEY", "EMBEDDINGS_MODEL"):
        value = os.environ.get(name, values.get(name))
        if not value:
            raise ValueError(f"Set {name} in .env or the environment")
        settings[name] = value
    if not settings["EMBEDDINGS_BASE_URL"].endswith("/v1"):
        raise ValueError("EMBEDDINGS_BASE_URL must end in /v1")
    return settings


def vector_text(vector):
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ValueError("Embedding must contain finite values")
    if not any(value != 0 for value in vector):
        raise ValueError("Embedding must be nonzero for cosine similarity")
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def embed(texts, settings):
    response = httpx.post(
        settings["EMBEDDINGS_BASE_URL"] + "/embeddings",
        headers={"Authorization": "Bearer " + settings["EMBEDDINGS_API_KEY"]},
        json={"model": settings["EMBEDDINGS_MODEL"], "input": texts},
        timeout=120, follow_redirects=False,
    )
    response.raise_for_status()
    data = response.json()
    items = sorted(data["data"], key=lambda item: item["index"])
    if [item["index"] for item in items] != list(range(len(texts))):
        raise ValueError("Embedding API returned unexpected indexes")
    return [item["embedding"] for item in items], data.get("usage", {}).get("total_tokens", 0)
