<!-- Atlas × Terminal repair report; commands reproduce checks and artifact paths identify live versus isolated-fixture screenshots. -->
The repair keeps the existing Atlas × Terminal design and all backend behavior. Verification uses the running application at http://127.0.0.1:8000 with its actual 159-role queue, plus an isolated database fixture for persistence actions. No production decisions or profile data were changed during review. Database tests use jagent_test on port 5434; port 5433 was not accessed.

Diagnosis was performed before editing: dashboard.css, workspace.js, all Jinja templates, existing screenshots, served HTML/CSS, Chromium console/network responses, actual DOM, computed styles, widths, overflow, and initialization were inspected.

Confirmed causes and repairs:

- The desktop sidebar and two-column composition persisted down to 761px. At 768px the sidebar consumed 185px, leaving a 539px workspace and only 298px for intelligence. Navigation now switches to a full-width header below 1200px. At 900px and below, CSS and JavaScript both use deliberate list/detail navigation. Phone navigation uses two columns of whole labels and a separate Source health link.
- Global link overflow-wrap:anywhere also affected brand and navigation, without nowrap protection. Brand and navigation now explicitly preserve whole labels; navigation tests check clipping, overlap and target geometry. Content such as long job headings can still wrap.
- The 15px root and small rem sizes produced 8.7px score suffixes, 8.55px intermediate panel labels and 11.4px mobile navigation. Root/body text is now 16px, job titles about 17px, company/location metadata 14px, and the smallest annotation type 12px. Controls have usable heights; phone decision fields stack.
- Search kept sharing one compressed desktop row at tablet width. Search now has its own line in list/detail mode, with sort and submit aligned beneath it.
- Applied had invalid heading nesting inside a span within summary, and all notes were hidden in collapsed details. Its summary now uses valid phrasing content with an accessible heading role; notes appear in the summary when present. Existing briefs still expand. The live database has one application and no note for that application; blank space below that single record is not missing data.
- Profile/Preferences used a narrow editor and a disproportionately wide guide. Forms now get three quarters of the desktop content width, grouped preference fields share two columns, guides use consistent rules, and the profile editor has a practical initial height. Tablet/phone forms use the available width and stack intentionally.
- Health now uses coordinated import/source sections and compact, separated source diagnostic rows, with responsive metadata columns.
- Previous browser assertions checked existence/visibility and page overflow without measuring rows, navigation geometry or panel widths. Strengthened checks cover these properties and blocked-script fallback; browser fixtures include long job titles and employer names.

Not reproduced: a continuous stream of blue links, missing stylesheet rules, legacy CSS overrides, or a failed selection initializer in a fresh Chromium session. The live stylesheet returned 200, there was one stylesheet, index-row computed to display:block, the workspace computed to grid on desktop, and selection initialized. No unexpected DOM nesting was found in the queue. There were no initial browser errors. A stale/mismatched asset cannot be established as the cause of the reported unstyled screenshot. Both asset URLs now carry a repair version to request fresh assets; this is a precaution, not a proven diagnosis.

Files changed specifically in this repair:

| File | Repair |
| --- | --- |
| jagent/static/dashboard.css | Typography, navigation widths/breakpoints, index/detail composition, controls, forms, application rows, diagnostics |
| jagent/static/workspace.js | Align list/detail media query with CSS at 900px |
| jagent/templates/base.html | Version CSS/JS URLs |
| jagent/templates/applied.html | Valid, structured summary with visible note preview |
| jagent/templates/health.html | Shared diagnostic layout and source-error class |
| tests/workspace_browser.py | Geometry, typography, controls, all requested widths, console/assets, persistence and script-failure acceptance |
| tests/test_dashboard.py | Long realistic headings and employers in the browser-only temporary fixture |
| tests/workspace_visual_review.py | Reproducible, read-only live-browser measurements and screenshots |
| docs/ui-repair.md | This evidence record |

Other files already modified before this task were preserved. No dependency, framework, schema, matching, source integration or persistence implementation was added or changed by this repair.

Commands and outputs (run from /home/egigj/jagent):

A — live geometry, selection, asset/console checks and screenshot capture:

```sh
/home/egigj/.cache/uv/archive-v0/n169s7cegO4KK6xL/bin/python tests/workspace_visual_review.py http://127.0.0.1:8000 > /tmp/jagent-atlas-repair/live-checks.txt
```

Captured output:

```text
PASS live opportunities 390px: no overflow; navigation single-line, separate, 44px targets; distinct rows; correct selection; intentional panel mode
PASS live applied 390px: no overflow; navigation single-line, separate, 44px targets
PASS live profile 390px: no overflow; navigation single-line, separate, 44px targets
PASS live filters 390px: no overflow; navigation single-line, separate, 44px targets
PASS live health 390px: no overflow; navigation single-line, separate, 44px targets
PASS live opportunities 768px: no overflow; navigation single-line, separate, 44px targets; distinct rows; correct selection; intentional panel mode
PASS live applied 768px: no overflow; navigation single-line, separate, 44px targets
PASS live profile 768px: no overflow; navigation single-line, separate, 44px targets
PASS live filters 768px: no overflow; navigation single-line, separate, 44px targets
PASS live health 768px: no overflow; navigation single-line, separate, 44px targets
PASS live opportunities 1024px: no overflow; navigation single-line, separate, 44px targets; distinct rows; correct selection; intentional panel mode
PASS live applied 1024px: no overflow; navigation single-line, separate, 44px targets
PASS live profile 1024px: no overflow; navigation single-line, separate, 44px targets
PASS live filters 1024px: no overflow; navigation single-line, separate, 44px targets
PASS live health 1024px: no overflow; navigation single-line, separate, 44px targets
PASS live opportunities 1440px: no overflow; navigation single-line, separate, 44px targets; distinct rows; correct selection; intentional panel mode
PASS live applied 1440px: no overflow; navigation single-line, separate, 44px targets
PASS live profile 1440px: no overflow; navigation single-line, separate, 44px targets
PASS live filters 1440px: no overflow; navigation single-line, separate, 44px targets
PASS live health 1440px: no overflow; navigation single-line, separate, 44px targets
PASS live: no console errors, uncaught errors or failed HTTP responses
```

B — complete test suite, including isolated Chromium interaction/persistence and fallback checks:

```sh
JAGENT_BROWSER_PYTHON=/home/egigj/.cache/uv/archive-v0/n169s7cegO4KK6xL/bin/python .venv/bin/python /tmp/jagent-run-tests.py -q > /tmp/jagent-atlas-repair/tests.txt
```

Captured output:

```text
........................................................................ [ 18%]
........................................................................ [ 37%]
........................................................................ [ 55%]
........................................................................ [ 74%]
........................................................................ [ 92%]
............................                                             [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/egigj/jagent/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
388 passed, 1 warning in 31.83s
```

C — JavaScript syntax:

```sh
node --check jagent/static/workspace.js
```

Output: none; exit 0.

D — diff whitespace:

```sh
git diff --check
```

Output: none; exit 0.

Each definition-of-done check:

| Check | Exact command reference and evidence/output |
| --- | --- |
| 1. Readable aligned navigation | A: all 20 page/width checks print “navigation single-line, separate, 44px targets”. B also checks brand and link clipping. Screenshots inspected. |
| 2. Distinct opportunity index | A: all four opportunity checks print “distinct rows”. B checks block display, no link underlines, separated row geometry and selected state. Live queue contains 159 roles and scrolls on desktop. Screenshots inspected. |
| 3. Usable intelligence | A: all four opportunity checks print “correct selection; intentional panel mode”. Desktop intelligence exceeds 500px at both requested desktop widths; selected ID, title and employer match. B checks links, analysis, Save and reachable decision controls. Screenshots of upper and lower detail inspected. |
| 4. Typography/spacing | A: no overflow at every page/width. B checks 16px body and readable location metadata. Visual review caught and repaired narrow phone decision fields. Screenshots inspected. |
| 5. Responsive layouts | A covers 390/768/1024/1440; B additionally covers 320. Navigation changes shape and tablet/phone use a back-to-index interaction. Screenshots inspected. |
| 6. Secondary pages | A prints PASS for Applied/Profile/Preferences (filters)/Health at every width; B also exercises form saves and saved application notes. Screenshots inspected, including an expanded real application and populated source diagnostics. |
| 7. Functionality | B: 388 passed. Chromium checks selection, keyboard, search, filters, error recovery, Save/Skip/Apply persistence, profile/preference saves, JavaScript disabled and enhancement script blocked. C/D exit 0. |

Screenshot paths:

- Live screenshots: /tmp/jagent-atlas-repair/live/.
- At each width W = 390, 768, 1024, 1440: opportunities-index-W.png, opportunities-selected-W.png, opportunities-decisions-W.png; applied-W.png and applied-expanded-W.png; profile-W.png; filters-W.png; health-W.png. Secondary pages also have PAGE-viewport-W.png captures so readable first-screen details can be inspected without shrinking tall full-page captures.
- Isolated-fixture screenshots: /tmp/jagent-atlas-repair/fixtures/ with index, selected, decision and secondary-page screenshots at 320/390/768/1024/1440, plus opportunities-desktop.png and no-javascript-390.png. Fixture shots deliberately include long role/employer names and saved application notes.
- Raw logs: /tmp/jagent-atlas-repair/live-checks.txt and /tmp/jagent-atlas-repair/tests.txt.

Visual inspection: used the image viewer on actual screenshot files, including the four selected-opportunity sizes, index rows, phone decision controls, long fixture titles, secondary forms at mobile/tablet/desktop, expanded applications and source diagnostics. The initial phone skip field was visibly clipped and was fixed before final capture. Screenshots, not screenshot command completion, informed the repairs.

Remaining limitations: the original blue-link/unstyled rendering failure was not reproduced and its delivery/cache cause remains unconfirmed. Current fresh-session screenshots and browser responses demonstrate styled rows and functioning panels. One existing Starlette/httpx deprecation warning remains; no dependency was added to address it. Browser verification uses Chromium, without a cross-browser or screen-reader audit.
