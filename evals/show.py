# Read-only fixture viewer; posting_id selects the job, recording, and converted claim indices.
import argparse
import re

from evals.compare import convert
from evals.data import ROOT, job_text, load
from jagent.briefing.evidence import job_excerpts, profile_excerpts
from jagent.profile import split_sections


def show(posting_id):
    posting = load(ROOT / "postings" / f"{posting_id}.fixture")
    output = load(ROOT / "outputs" / f"{posting_id}.fixture")
    profile = (ROOT / "profile.md").read_text().split("\n", 1)[1]
    text = job_text(posting)
    jobs = job_excerpts(text)
    profiles = profile_excerpts(profile)
    drafts, _ = convert(output, jobs, profiles)
    analysis = output.get("analysis") or {}
    origins = {}
    # Keep the first sentence producing each kind/skill pair, matching converter deduplication.
    for sentence in re.findall(r".+?(?:[.!?](?=\s|$)|$)", analysis.get("explanation", ""), flags=re.S):
        sentence = sentence.strip()
        candidates, _ = convert({"analysis": {**analysis, "explanation": sentence}}, jobs, profiles)
        for draft in candidates:
            origins.setdefault((draft.kind, draft.skill), sentence)
    print(f"Posting {posting_id}\n\nJob text\n{text}")
    print("\nSynthetic profile")
    for heading, body in split_sections(profile):
        print(f"\n## {heading}\n{body}")
    print("\nConverted claims")
    for index, draft in enumerate(drafts):
        print(f"{index} | {draft.kind} | {draft.skill}")
        print(f"Explanation: {origins[(draft.kind, draft.skill)]}")
    if not drafts:
        print("No converted claims.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show a frozen posting and its converted claims")
    parser.add_argument("posting_id", type=int)
    args = parser.parse_args()
    try:
        show(args.posting_id)
    except FileNotFoundError as error:
        parser.exit(1, f"Fixture not found: {error.filename}\n")
