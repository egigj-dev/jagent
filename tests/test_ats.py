# ATS discovery tests; SAMPLES holds public board URLs and expected platform-slug pairs.
from jagent.sources.ats import extract_company_slugs


def test_extracts_public_board_slugs_from_urls():
    samples = """
    https://boards.greenhouse.io/company-2bed2032ed3d/jobs/123
    https://job-boards.greenhouse.io/company-822b33ad87c1/jobs/456
    https://jobs.lever.co/company-9ef809f3a65b/abc
    https://jobs.ashbyhq.com/company-31f61ed3e6e2/def
    https://jobs.smartrecruiters.com/company-9d388ac0a81e/ghi
    """
    assert extract_company_slugs(samples) == {
        ("greenhouse", "company-2bed2032ed3d"),
        ("greenhouse", "company-822b33ad87c1"),
        ("lever", "company-9ef809f3a65b"),
        ("ashby", "company-31f61ed3e6e2"),
        ("smartrecruiters", "company-9d388ac0a81e"),
    }
