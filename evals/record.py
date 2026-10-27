# Record one existing analysis call per posting; usage and elapsed seconds come from the actual response.
from datetime import UTC, datetime
import time
from unittest.mock import patch

import httpx

from evals.data import ROOT, job_text, load, save
from jagent import analysis
from jagent.briefing.evidence import text_version

PRICING = {
    "model": "deepseek/deepseek-v4.1-flash", "input_per_million": 0.18,
    "output_per_million": 0.72, "checked_at": "2026-10-27",
    "source": "https://www.tokenrouter.com/models/deepseek/deepseek-v4.1-flash/",
}


def record(root=ROOT):
    settings = analysis.llm_settings()
    profile = (root / "profile.md").read_text().split("\n", 1)[1]
    post = httpx.post
    for path in sorted((root / "postings").glob("*.fixture")):
        target = root / "outputs" / path.name
        if target.exists():
            previous = load(target)
            # A rate-limited request produced no analysis; resume it without regenerating successful outputs.
            if previous.get("error") != "http_429" or previous.get("content"):
                print(f"Already recorded: {path.stem}", flush=True)
                continue
        posting = load(path)
        usage = {}

        def capture(*args, **kwargs):
            response = post(*args, **kwargs)
            if response.is_success:
                usage.update(response.json().get("usage", {}))
            return response

        started = time.perf_counter()
        result = {"posting_id": posting["id"], "model": settings["LLM_MODEL"],
                  "job_snapshot_id": text_version(job_text(posting)),
                  "profile_version": text_version(profile), "recorded_at": datetime.now(UTC).isoformat(),
                  "content": "", "analysis": None, "error": None}
        try:
            with patch.object(analysis.httpx, "post", capture):
                content, tokens = analysis.chat(analysis.job_input(posting), profile, settings)
            result["content"] = content
            result["total_tokens"] = tokens
            result["analysis"] = analysis.parse_analysis(content).model_dump()
        except (httpx.HTTPError, ValueError) as error:
            result["error"] = analysis.error_type(error)
        result["latency_seconds"] = round(time.perf_counter() - started, 6)
        result["usage"] = usage
        result["cost_usd"] = usage.get("cost")
        if result["cost_usd"] is None and settings["LLM_MODEL"] == PRICING["model"] and usage:
            result["cost_usd"] = (usage["prompt_tokens"] * PRICING["input_per_million"]
                                  + usage["completion_tokens"] * PRICING["output_per_million"]) / 1_000_000
            result["cost_basis"] = {"kind": "published rate estimate", **PRICING}
        save(target, result, "Recorded baseline response; model, usage, cost and latency describe one request.")
        print(f"Recorded {path.stem}: tokens={result.get('total_tokens', 0)} error={result['error']}", flush=True)
        time.sleep(analysis.REQUEST_PAUSE_SECONDS)


if __name__ == "__main__":
    record()
