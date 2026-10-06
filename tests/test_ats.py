# ATS discovery tests; SAMPLES holds public board URLs and expected platform-slug pairs.
from jagent.sources.ats import extract_company_slugs


def test_extracts_public_board_slugs_from_urls():
    samples = """
    https://boards.greenhouse.io/stripe/jobs/123
    https://job-boards.greenhouse.io/acme/jobs/456
    https://jobs.lever.co/leverco/abc
    https://jobs.ashbyhq.com/notion/def
    https://jobs.smartrecruiters.com/SmartRecruiters/ghi
    """
    assert extract_company_slugs(samples) == {
        ("greenhouse", "stripe"),
        ("greenhouse", "acme"),
        ("lever", "leverco"),
        ("ashby", "notion"),
        ("smartrecruiters", "smartrecruiters"),
    }
