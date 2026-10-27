# Evidence checks; SYNONYMS contains lexical aliases and excerpt IDs bind claims to frozen inputs.
import hashlib
import re
import unicodedata

from jagent.briefing.contract import Claim, ClaimDraft
from jagent.profile import split_sections

SYNONYMS = {
    "Kubernetes": ("kubernetes", "k8s"),
    "PostgreSQL": ("postgresql", "postgres"),
    "JavaScript": ("javascript", "js"),
    "TypeScript": ("typescript", "ts"),
    "Python": ("python",),
    "SQL": ("sql",),
    "Docker": ("docker",),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure",),
    "Terraform": ("terraform",),
    "PyTorch": ("pytorch",),
    "TensorFlow": ("tensorflow",),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "Linux": ("linux",),
    "Git": ("git",),
    "React": ("react", "reactjs", "react.js"),
    "Java": ("java",),
    "C++": ("c++",),
    "C#": ("c#", "csharp"),
    "Go": ("go", "golang"),
    "R": ("r",),
}


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def text_version(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()[:12]


def excerpts(text: str) -> list[str]:
    # Wrapped prose stays together; blank lines and bullet lines delimit evidence.
    result = []
    paragraph = []
    for line in unicodedata.normalize("NFKC", text).splitlines():
        bullet = re.match(r"^\s*(?:[-*•]|\d+[.)])\s+", line)
        if not line.strip() or bullet:
            if paragraph:
                result.append(normalize(" ".join(paragraph)))
                paragraph = []
            if bullet:
                result.append(normalize(line[bullet.end():]))
        else:
            paragraph.append(line)
    if paragraph:
        result.append(normalize(" ".join(paragraph)))
    return result


def job_excerpts(text: str) -> dict[str, str]:
    snapshot = text_version(text)
    return {f"job:{snapshot}:{i}": value for i, value in enumerate(excerpts(text))}


def profile_excerpts(text: str) -> dict[str, str]:
    result = {}
    for section, body in split_sections(text):
        # Continue numbering if a profile repeats a section heading.
        offset = sum(key.startswith(f"profile:{section}:") for key in result)
        result.update({f"profile:{section}:{offset + i}": value
                       for i, value in enumerate(excerpts(body))})
    return result


def mentions(text: str, skill: str) -> bool:
    skill = normalize(skill)
    if not skill:
        return False
    aliases = next((values for values in SYNONYMS.values()
                    if skill.casefold() in (value.casefold() for value in values)), (skill,))
    text = normalize(text)
    for alias in aliases:
        # Symbol boundaries prevent C++/C# matching C or each other; Go/R need a technical context.
        pattern = rf"(?<![\w+#]){re.escape(alias)}(?![\w+#])"
        for match in re.finditer(pattern, text, re.I):
            if alias not in ("go", "r"):
                return True
            before, after = text[max(0, match.start() - 35):match.start()], text[match.end():match.end() + 35]
            if (re.search(r"(?:languages?|programming|skills?|stack|written in|using|with)\s*:?\s*$", before, re.I)
                    or re.match(r"\s+(?:programming|language|developer|development|experience|engineer)\b", after, re.I)
                    or re.search(r"(?:Python|Java|SQL|C\+\+)\s*[,/]\s*$", before, re.I)
                    or re.match(r"\s*[,/]\s*(?:Python|Java|SQL|C\+\+)", after, re.I)):
                return True
    return False


def failed_rules(draft: ClaimDraft, jobs: dict[str, str], profiles: dict[str, str], full_profile_text: str) -> list[int]:
    failures = []
    job = jobs.get(draft.job_excerpt_id)
    profile = profiles.get(draft.profile_excerpt_id)
    if job is None:
        failures.append(1)
    if ((draft.kind == "strength" and profile is None)
            or (draft.kind == "not_demonstrated" and draft.profile_excerpt_id is not None)):
        failures.append(2)
    # Missing citations fail their existence rule, rather than double-counting mention rules.
    if job is not None and not mentions(job, draft.skill):
        failures.append(3)
    if draft.kind == "strength" and profile is not None and not mentions(profile, draft.skill):
        failures.append(4)
    if draft.kind == "not_demonstrated" and mentions(full_profile_text, draft.skill):
        failures.append(5)
    return failures


def check(draft: ClaimDraft, job_excerpts: dict[str, str], profile_excerpts: dict[str, str], full_profile_text: str) -> Claim:
    status = "flagged" if failed_rules(draft, job_excerpts, profile_excerpts, full_profile_text) else "passed_checks"
    return Claim(**draft.model_dump(), status=status)
