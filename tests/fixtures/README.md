<!-- remoteok.json is the unmodified API response; its first item contains metadata. -->
remoteok.json was downloaded from https://remoteok.com/api on 2026-10-04.
It remains valid JSON without a leading comment. Remote OK attribution and API
terms are preserved in its metadata, and each posting retains its source URL.

The following additional responses were downloaded on 2026-10-04 and saved
without modification (JSON and XML fixtures retain their native formats):

- remotive.json: https://remotive.com/api/remote-jobs?category=software-dev
- arbeitnow.json: https://www.arbeitnow.com/api/job-board-api
- himalayas.json: https://himalayas.app/jobs/api
- jobicy.json: https://jobicy.com/api/v2/remote-jobs
- weworkremotely.xml: https://weworkremotely.com/remote-jobs.rss
- hn_hiring_search.json: https://hn.algolia.com/api/v1/search?tags=story,author_whoishiring&query=Ask%20HN%3A%20Who%20is%20hiring%3F&hitsPerPage=1000
- hn_hiring.json: https://hn.algolia.com/api/v1/items/49922569
- staffal.html: https://staff.al/sq/job-list
- kosovajob.html: https://kosovajob.com/
- djinni.html: https://djinni.co/jobs/

Remotive and Jobicy dates without an explicit offset are interpreted as UTC.

Pagination evidence checked on 2026-10-04:

- The saved Himalayas response has `limit: 20`, `totalCount: 116518`, and
  `nextCursor`. Its `comments` field explains passing that value as `cursor`.
  https://himalayas.app/api documents the 20-job maximum and cursor pagination.
- The saved Remotive response has `job-count: 18` and `total-job-count: 18`.
  https://github.com/remotive-com/remote-jobs-api documents `limit` as optional
  with default `all`; no pagination parameters are documented.
- Himalayas follows cursors with a one-second delay after each page. When there
  are existing Himalayas postings, it stops after processing a page containing
  a known source ID. Only the initial sync uses the seven-day UTC cutoff.
  Remotive retrieves every job in the category response without a date filter.

Ordering evidence: `himalayas_order.json` is an unmodified response from
https://himalayas.app/jobs/api?limit=20 saved on 2026-10-05. All 20 `pubDate`
values are non-increasing, from 1791218495 to 1791217761, confirming newest-first
ordering in that response.

The Staff.al listing request currently returns a Next.js 404 shell with no job
cards. Its adapter uses the public sitemap as a fallback index, then reads new
job details for title, company, and description. The KosovoJob listing cards
also omit descriptions, so their detail pages are read only for unseen jobs.
Djinni cards contain job descriptions and need no detail-page requests.
