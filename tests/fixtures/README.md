<!-- remoteok.json is the trimmed API response; its first item contains metadata. -->
remoteok.json was downloaded from the Remote OK API on 2026-10-04.
It remains valid JSON without a leading comment. Remote OK attribution and API
terms remain in its metadata. Employer identities, contacts and company-specific
URL components use deterministic placeholders; source domains remain intact.
Original responses remain in history at commit `0287af0`. The per-posting audit
uses identifier digests rather than publishing an employer-name dictionary.

The following additional responses were downloaded on 2026-10-04 and saved
as samples (JSON and XML fixtures retain their native formats):

- remotive.json: Remotive software-development feed
- arbeitnow.json: Arbeitnow job-board API
- himalayas.json: https://himalayas.app/jobs/api
- jobicy.json: https://jobicy.com/api/v2/remote-jobs
- weworkremotely.xml: https://weworkremotely.com/remote-jobs.rss
- hn_hiring_search.json: HN Algolia hiring-thread search
- hn_hiring.json: https://hn.algolia.com/api/v1/items/49922569
- staffal.html: https://staff.al/sq/job-list
- kosovajob.html: https://kosovajob.com/
- djinni.html: https://djinni.co/jobs/

Remotive and Jobicy dates without an explicit offset are interpreted as UTC.

Pagination evidence checked on 2026-10-04:

- The saved Himalayas response has `limit: 20`, `totalCount: 116518`, and
  `nextCursor`. Its `comments` field explains passing that value as `cursor`.
  https://himalayas.app/api documents the 20-job maximum and cursor pagination.
- The saved Remotive response has `job-count: 18` and `total-job-count: 18` (original response metadata).
  The Remotive API documentation describes `limit` as optional
  with default `all`; no pagination parameters are documented.
- Himalayas follows cursors with a one-second delay after each page. When there
  are existing Himalayas postings, it stops after processing a page containing
  a known source ID. Only the initial sync uses the seven-day UTC cutoff.
  Remotive retrieves every job in the category response without a date filter.

Ordering evidence: `himalayas_order.json` is a trimmed response from
https://himalayas.app/jobs/api?limit=20 saved on 2026-10-05. The five retained `pubDate`
values are non-increasing, confirming newest-first
ordering in that response.

The Staff.al listing request currently returns a Next.js 404 shell with no job
cards. Its adapter uses the public sitemap as a fallback index, then reads new
job details for title, company, and description. The KosovoJob listing cards
also omit descriptions, so their detail pages are read only for unseen jobs.
Djinni cards contain job descriptions and need no detail-page requests.

Release samples retain at most five postings per file; Remote OK also retains
its attribution metadata. Counts and pagination metadata describe the original
responses. HN replies and excess search hits are removed; HTML samples keep at
most five cards and omit executable scripts. Staff.al has no job cards. JSON, XML
and HTML retain native syntax rather than adding nonstandard comment fields.
