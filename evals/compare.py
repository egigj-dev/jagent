# Offline baseline evaluation; SKILLS bounds lexical extraction and labels remain separate human judgments.
from collections import Counter
import re
import sys

from jagent.briefing.contract import ClaimDraft, InputPacket
from jagent.briefing.evidence import (
    SYNONYMS, check, failed_rules, job_excerpts, mentions, normalize,
    profile_excerpts, text_version,
)
from evals.data import ROOT, job_text, load

SKILLS = tuple(SYNONYMS)
NEGATIVE = re.compile(r"\b(?:lack\w*|missing|not\s+(?:shown|demonstrated|evident|mentioned|documented|listed)|no\s+(?:evidence|experience)|without|gap\w*|absen\w*)\b", re.I)


def mapped_excerpt(quote, excerpts):
    if not quote:
        return "missing"
    quote = normalize(quote).casefold()
    return next((key for key, value in excerpts.items() if quote in normalize(value).casefold()), "missing")


def convert(output, jobs, profiles):
    analysis = output.get("analysis") or {}
    drafts = []
    unmapped = []
    explanation = analysis.get("explanation", "")
    for clause in re.split(r"[.;!?]|\b(?:but|however|while|although)\b", explanation, flags=re.I):
        for skill in SKILLS:
            if not mentions(clause, skill):
                continue
            kind = "not_demonstrated" if NEGATIVE.search(clause) else "strength"
            if any(draft.skill == skill and draft.kind == kind for draft in drafts):
                continue
            quotes = [quote for quote in analysis.get("evidence", {}).values()
                      if quote and mentions(quote, skill)]
            # Fit explanations have no citations; an absent matching quote must remain unmapped.
            job_id = next((mapped_excerpt(quote, jobs) for quote in quotes
                           if mapped_excerpt(quote, jobs) != "missing"), "missing")
            profile_id = None
            if kind == "strength":
                profile_id = next((mapped_excerpt(quote, profiles) for quote in quotes
                                   if mapped_excerpt(quote, profiles) != "missing"), "missing")
            draft = ClaimDraft(kind=kind, skill=skill, job_excerpt_id=job_id,
                               profile_excerpt_id=profile_id)
            drafts.append(draft)
            reasons = []
            if job_id == "missing":
                reasons.append("no matching verbatim job quote")
            if profile_id == "missing":
                reasons.append("no matching verbatim profile quote")
            if reasons:
                unmapped.append((skill, "; ".join(reasons)))
    return drafts, unmapped


def adversarial_pass(posting, output, drafts, jobs, profiles, profile):
    if not output.get("analysis"):
        return False
    content = normalize(output["content"]).casefold()
    expected = posting["adversarial"]
    if any(term.casefold() in content for term in expected["forbidden_terms"]):
        return False
    injected = normalize(expected["injection"])
    if any(draft.job_excerpt_id in jobs and normalize(jobs[draft.job_excerpt_id]) == injected
           for draft in drafts):
        return False
    cited = " ".join(profiles.get(draft.profile_excerpt_id, "") for draft in drafts)
    # Exact eight-word spans detect copied profile prose beyond the cited excerpts.
    words = normalize(profile).casefold().split()
    cited = normalize(cited).casefold()
    return not any(" ".join(words[i:i + 8]) in content and " ".join(words[i:i + 8]) not in cited
                   for i in range(len(words) - 7))


def evaluate(root=ROOT):
    profile = (root / "profile.md").read_text().split("\n", 1)[1]
    profiles = profile_excerpts(profile)
    total = flagged = labeled = unsupported = missed = unmapped_count = 0
    rule_counts = Counter()
    latencies, costs = [], []
    adversarial = []
    details = []
    missing_outputs = 0
    failed_outputs = 0
    for path in sorted((root / "postings").glob("*.fixture")):
        posting = load(path)
        output_path = root / "outputs" / path.name
        if not output_path.exists():
            missing_outputs += 1
            continue
        output = load(output_path)
        failed_outputs += output.get("analysis") is None
        text = job_text(posting)
        packet = InputPacket(posting_id=posting["id"], job_snapshot_id=text_version(text),
                             profile_version=text_version(profile), model=output["model"])
        if output["job_snapshot_id"] != packet.job_snapshot_id or output["profile_version"] != packet.profile_version:
            raise ValueError(f"Recording input mismatch: {path.name}")
        jobs = job_excerpts(text)
        drafts, unmapped = convert(output, jobs, profiles)
        unmapped_count += len(unmapped)
        details.extend(f"{path.stem}: {skill}: {reason}" for skill, reason in unmapped)
        labels = load(root / "labels" / path.name)
        for index, draft in enumerate(drafts):
            total += 1
            flagged += check(draft, jobs, profiles, profile).status == "flagged"
            rule_counts.update(failed_rules(draft, jobs, profiles, profile))
            label = labels["claims"].get(str(index))
            if label in ("supported", "unsupported"):
                labeled += 1
                unsupported += label == "unsupported"
        if labels["missed_requirements"] is not None:
            missed += len(labels["missed_requirements"])
        if posting.get("adversarial"):
            adversarial.append((path.stem, adversarial_pass(posting, output, drafts, jobs, profiles, profile)))
        latencies.append(output["latency_seconds"])
        if output.get("cost_usd") is not None:
            costs.append(output["cost_usd"])
    print("Baseline | Value")
    print(f"Recordings | {len(latencies)}; missing {missing_outputs}")
    print(f"Analysis outputs | {len(latencies) - failed_outputs} valid; {failed_outputs} failed requests")
    print(f"Claims total | {total}")
    print(f"Claims flagged | {flagged}/{total}")
    for rule in range(1, 6):
        print(f"Flagged by rule {rule} | {rule_counts[rule]}/{total} ({100 * rule_counts[rule] / max(1, total):.1f}%)")
    print(f"Unmapped claims | {unmapped_count}")
    print(f"Human labels | {labeled} labeled claims; {total - labeled} unlabeled")
    print(f"Unsupported rate | {unsupported}/{labeled}" if labeled else "Unsupported rate | N/A (0 labeled claims)")
    labeled_cases = sum(load(path)["missed_requirements"] is not None for path in (root / "labels").glob("*.fixture"))
    print(f"Missed requirements | {missed} ({labeled_cases} labeled cases)" if labeled_cases else "Missed requirements | N/A (0 labeled cases)")
    for name, passed in adversarial:
        print(f"Adversarial {name} | {'PASS' if passed else 'FAIL'}")
    print(f"Mean cost USD (estimated) | {sum(costs) / len(costs):.8f} ({len(costs)} priced recordings)" if costs else "Mean cost USD | N/A (provider returned no cost)")
    print(f"Mean latency seconds | {sum(latencies) / len(latencies):.3f}" if latencies else "Mean latency seconds | N/A")
    print("\nSeeded checks | Flagged / total")
    seeds = load(root / "seeded.fixture")
    bad = good = bad_flagged = good_flagged = 0
    for case in seeds["cases"]:
        draft = ClaimDraft.model_validate(case["draft"])
        flagged = check(draft, seeds["job_excerpts"], seeds["profile_excerpts"], seeds["profile"]).status == "flagged"
        if case["failed_rules"]:
            bad += 1
            bad_flagged += flagged
        else:
            good += 1
            good_flagged += flagged
    print(f"Seeded faults | {bad_flagged} / {bad}")
    print(f"Valid controls wrongly flagged | {good_flagged} / {good}")
    for detail in details:
        print("Unmapped:", detail)
    return bad_flagged == bad and good_flagged == 0 and missing_outputs == 0 and failed_outputs == 0


if __name__ == "__main__":
    from pathlib import Path
    raise SystemExit(0 if evaluate(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT) else 1)
