# Dashboard tests; temporary tables isolate reviews/profile versions and fake API calls forbid network use.
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
import os
import json
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
import pytest

from jagent import cli, dashboard, health
from jagent.db import connect
from jagent.filters import LOCAL_FILTER_DEFAULTS


@pytest.fixture(autouse=True)
def source_health(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard, "check_health", lambda: [])
    monkeypatch.setattr(dashboard, "duapune_freshness", lambda: "Fresh: fixture")
    import_path = tmp_path / "duapune.json"
    import_path.write_text(json.dumps({"collected_at": datetime.now(UTC).isoformat()}))
    monkeypatch.setattr(health.duapune, "IMPORT_PATH", import_path)


@pytest.fixture
def dashboard_db(monkeypatch):
    if os.environ.get("JAGENT_TEST_POSTGRES") != "1":
        pytest.skip("Set JAGENT_TEST_POSTGRES=1 to test dashboard in temporary tables")
    with connect() as connection:
        schema = (Path(__file__).resolve().parent.parent / "schema.sql").read_text()
        for name in ("postings", "profile", "profile_sections", "matches", "posting_analysis", "reviews", "pipeline_runs"):
            start = schema.index(f"CREATE TABLE IF NOT EXISTS {name} (")
            statement = schema[start:schema.index(";", start)+1]
            connection.execute(statement.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE"))
        connection.execute("ALTER TABLE matches ADD COLUMN explanation text")
        connection.execute("""
            INSERT INTO profile(text,filters) VALUES ('## Engineering\nPython\n## Languages\nEnglish',
              '{"countries":["albania"],"remote_regions":[],"remote_excluded":[],"exclude_title_keywords":[]}');
            INSERT INTO profile_sections(profile_id,name,text,embedding,embedding_model)
              VALUES (1,'Engineering','Python','[1,0]','fake'),(1,'Languages','English','[0,1]','fake');
        """)
        for id in (1,2,3):
            connection.execute("""
                INSERT INTO postings(id,source,source_id,title,company,locations,first_seen,
                    embedding,embedding_model,url,other_urls)
                VALUES (%s,'sample',%s,%s,'Acme','{Albania}',%s,'[1,0]','fake',
                    'https://example.com/job','{https://example.org/company-d9298a10d1b0}')
            """, (id,str(id),f"Engineer {id}",datetime.now(UTC)))
            connection.execute("""
                INSERT INTO matches(posting_id,profile_id,similarity,matched_section,percentile,queued,explanation)
                VALUES (%s,1,%s,'Engineering',100,true,'Python fits. Cloud is missing.')
            """, (id,1-id/10))
        connection.execute("""
            UPDATE postings SET embedding='[0.8,0.6]' WHERE id=2;
            UPDATE postings SET embedding='[0.6,0.8]' WHERE id=3;
            INSERT INTO posting_analysis(posting_id,seniority,required_languages,employment_types,model)
            VALUES (1,'mid','{English}','{full_time}','llm'),
                   (2,'senior','{German}','{contract}','llm');
        """)
        connection.commit()
        monkeypatch.setattr(dashboard,"connect",lambda: nullcontext(connection))
        monkeypatch.setattr(health,"connect",lambda: nullcontext(connection))
        monkeypatch.setattr(dashboard,"embedding_settings",lambda: {"EMBEDDINGS_MODEL":"fake"})
        # All saves must use cached vectors, never any HTTP API.
        monkeypatch.setattr("httpx.post",Mock(side_effect=AssertionError("No API calls")))
        yield connection


@pytest.fixture
def client(dashboard_db):
    with TestClient(dashboard.app) as client:
        yield client


def test_review_persists_and_applied_page(client,dashboard_db):
    assert 'id="posting-1"' in client.get('/').text
    response=client.post('/reviews/1',data={"action":"apply","note":"Prepare CV"})
    assert response.status_code==200 and 'id="posting-1"' not in response.text
    assert 'id="posting-1"' not in client.get('/').text
    assert 'Engineer 1' in client.get('/applied').text and 'Prepare CV' in client.get('/applied').text
    assert dashboard_db.execute('SELECT action,reason,note FROM reviews WHERE posting_id=1').fetchone()==('apply',None,'Prepare CV')


def test_skip_requires_reason_and_htmx_removes_card(client,dashboard_db):
    assert client.post('/reviews/1',data={"action":"skip"}).status_code==422
    response=client.post('/reviews/1',data={"action":"skip","reason":"salary"},headers={"HX-Request":"true"})
    assert response.status_code==200 and 'id="posting-1"' not in response.text
    assert dashboard_db.execute('SELECT action,reason FROM reviews WHERE posting_id=1').fetchone()==('skip','salary')


def test_later_moves_to_bottom_without_reranking(client,dashboard_db):
    response=client.post('/reviews/1',data={"action":"later"})
    assert response.text.index('id="posting-3"')<response.text.index('id="posting-1"')
    assert dashboard_db.execute('SELECT similarity FROM matches WHERE posting_id=1').fetchone()==(.9,)


def test_view_filters_are_explicit_and_do_not_rerank(client,dashboard_db):
    assert 'id="posting-2"' in client.get('/').text
    assert 'id="posting-2"' not in client.get('/?seniority=mid').text
    assert 'id="posting-2"' in client.get('/?views=1').text
    assert dashboard_db.execute('SELECT count(*) FROM matches WHERE queued').fetchone()==(3,)


@pytest.mark.parametrize('field,value',[
    ('seniority','lead'),('required_languages',['French']),('employment_types',['equity_only']),
])
def test_each_view_filter(field,value):
    posting={"seniority":"mid","required_languages":["Italian","Albanian"],"employment_types":["full_time"]}
    assert dashboard.visible(posting,dashboard.view_options({}))
    posting[field]=value
    assert not dashboard.visible(posting,dict.fromkeys(dashboard.VIEW_KEYS, True))
    assert dashboard.visible(posting,dashboard.view_options({"views":"1"}))


def test_filters_new_version_copies_embeddings_and_updates_queue(client,dashboard_db):
    response=client.post('/filters',data={"countries":" Japan , , Korea ","remote_regions":"worldwide",
                                         "remote_excluded":"us only","exclude_title_keywords":"sales"})
    assert response.status_code==200 and 'id="posting-1"' not in response.text
    profiles=dashboard_db.execute('SELECT id,text,filters FROM profile ORDER BY id').fetchall()
    assert len(profiles)==2 and profiles[0][1]==profiles[1][1]
    assert profiles[1][2]['countries']==['Japan','Korea']
    sections=dashboard_db.execute('SELECT name,text,embedding::text,embedding_model FROM profile_sections WHERE profile_id=%s ORDER BY name',(2,)).fetchall()
    assert sections==dashboard_db.execute('SELECT name,text,embedding::text,embedding_model FROM profile_sections WHERE profile_id=1 ORDER BY name').fetchall()
    # Allow Albania again: ranking runs in SQL and profile text/embeddings stay cached.
    response=client.post('/filters',data={"countries":"albania"})
    assert 'id="posting-1"' in response.text
    assert dashboard_db.execute('SELECT count(*) FROM matches WHERE profile_id=3 AND queued').fetchone()==(1,)
    assert dashboard_db.execute('SELECT explanation FROM matches WHERE profile_id=3 AND posting_id=1').fetchone()==('Python fits. Cloud is missing.',)


def test_local_preferences_save_and_badge_only_for_local_queue(client, dashboard_db):
    dashboard_db.execute("UPDATE postings SET title='Python Developer' WHERE id IN (1,2)")
    dashboard_db.execute("UPDATE postings SET embedding='[-1,0]' WHERE id=2")
    page = client.get('/filters').text
    assert 'name="local_locations"' in page and 'name="local_title_keywords"' in page
    assert 'albania, shqiperi, tirana, tirane' in page
    response = client.post('/filters', data={
        'countries': 'albania', 'local_locations': ' Albania , , Tiranë ',
        'local_title_keywords': ' Python , developer ',
    })
    assert response.status_code == 200
    filters, = dashboard_db.execute('SELECT filters FROM profile WHERE id=2').fetchone()
    assert filters['local_locations'] == ['Albania', 'Tiranë']
    assert filters['local_title_keywords'] == ['Python', 'developer']
    assert dashboard_db.execute(
        'SELECT queued FROM matches WHERE profile_id=2 AND posting_id=2'
    ).fetchone() == (True,)
    assert response.text.count('>Local</span>') == 1
    html = response.text.split('id="posting-2"', 1)[1].split('</article>', 1)[0]
    assert '>Local</span>' in html
    assert '>Local</span>' not in response.text.split('id="posting-1"', 1)[1].split('</article>', 1)[0]
    profile_page = client.get('/profile').text
    assert 'name="local_locations" value="Albania, Tiranë"' in profile_page
    response = client.post('/filters', data={'countries': 'albania',
                                           'local_locations': '', 'local_title_keywords': ''})
    assert '>Local</span>' not in response.text
    assert 'id="posting-2"' not in response.text


def test_local_badge_rechecks_current_preferences(client, dashboard_db):
    filters, = dashboard_db.execute('SELECT filters FROM profile WHERE id=1').fetchone()
    dashboard_db.execute('UPDATE profile SET filters=%s WHERE id=1',
                         (Jsonb(filters | LOCAL_FILTER_DEFAULTS),))
    dashboard_db.execute("UPDATE postings SET title='Python Developer' WHERE id=1")
    dashboard_db.execute('UPDATE matches SET percentile=62 WHERE posting_id=1')
    assert client.get('/').text.count('>Local</span>') == 1
    dashboard_db.execute("UPDATE profile SET filters=jsonb_set(filters, '{local_locations}', '[]')")
    assert '>Local</span>' not in client.get('/').text


def test_html_escapes_posting_text(client,dashboard_db):
    dashboard_db.execute("UPDATE postings SET title='<script>alert(1)</script>' WHERE id=1")
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in client.get('/').text


def test_serve_binds_localhost(monkeypatch):
    run=Mock()
    monkeypatch.setattr('uvicorn.run',run)
    monkeypatch.setattr('sys.argv',['jagent','serve'])
    assert cli.main()==0
    run.assert_called_once_with('jagent.dashboard:app',host='127.0.0.1',port=8000)


@pytest.mark.parametrize('deadline,expected', [
    (None, None), ('2026-10-14T21:59:00+00:00', 0),
    ('2026-10-17T21:59:00+00:00', 3), ('2026-10-18T21:59:00+00:00', 4),
    ('2026-10-13T21:59:00+00:00', 0),
])
def test_days_left_with_fixed_today(deadline, expected):
    today = datetime(2026, 10, 14, tzinfo=UTC).date()
    expires_at = datetime.fromisoformat(deadline) if deadline else None
    assert dashboard.days_left(expires_at, today) == expected


def test_duapune_card_days_left_and_closing_soon(client, dashboard_db, monkeypatch):
    today = datetime.now(UTC).date()
    monkeypatch.setitem(dashboard.templates.env.filters, 'days_left',
                        lambda expiry: dashboard.days_left(expiry, today))
    dashboard_db.execute("""
        UPDATE postings SET expires_at=CASE id WHEN 1 THEN %s ELSE %s END,
            source=CASE id WHEN 1 THEN 'duapune' ELSE source END WHERE id IN (1,3);
    """, (datetime.now(UTC) + timedelta(days=3), datetime.now(UTC) + timedelta(days=2)))
    default = client.get('/?views=1').text
    assert default.index('id="posting-1"') < default.index('id="posting-3"')
    assert 'deadline-urgent">3 days left' in default
    assert 'deadline-urgent">2 days left' in default
    assert default.count('days left') == 2
    response = client.get('/?views=1&sort=closing_soon')
    assert response.status_code == 200
    html = response.text
    assert html.index('id="posting-3"') < html.index('id="posting-1"') < html.index('id="posting-2"')
    assert 'value="closing_soon" selected' in html
    # Both HTMX and regular review submissions retain the selected sort.
    response = client.post('/reviews/3', data={
        'action': 'later', 'views': '1', 'sort': 'closing_soon',
    }, headers={'HX-Request': 'true'})
    assert response.text.index('id="posting-3"') < response.text.index('id="posting-1"')
    response = client.post('/reviews/1', data={
        'action': 'later', 'views': '1', 'sort': 'closing_soon',
    })
    assert response.text.index('id="posting-3"') < response.text.index('id="posting-1"')
    assert 'sort=closing_soon' in str(response.url)
    response = client.get('/?views=1&sort=closing_soon', headers={'HX-Request': 'true'})
    assert response.text.index('id="posting-3"') < response.text.index('id="posting-1"')


@pytest.mark.parametrize('htmx', [False, True])
@pytest.mark.parametrize('problems', [[], [
    'duapune: stale (latest run older than 36 hours)',
    'sample: status=error (<unavailable>)',
]])
def test_queue_shows_source_health_banner(monkeypatch, htmx, problems):
    health_check = Mock(return_value=problems)
    monkeypatch.setattr(dashboard, 'check_health', health_check)
    monkeypatch.setattr(dashboard, 'connect', lambda: nullcontext(None))
    monkeypatch.setattr(dashboard, 'postings_for_page', lambda *args, **kwargs: [])
    monkeypatch.setattr(dashboard, 'latest_pipeline_run', lambda: None)
    monkeypatch.setattr(dashboard, 'active_profile', lambda connection: None)
    with TestClient(dashboard.app) as client:
        response = client.get('/', headers={'HX-Request': 'true'} if htmx else {})
    assert response.status_code == 200
    health_check.assert_called_once_with()
    assert 'id="health-banner"' in response.text
    assert ('Source health problems' in response.text) == bool(problems)
    if problems:
        assert 'duapune: stale (latest run older than 36 hours)' in response.text
        assert '&lt;unavailable&gt;' in response.text
    if htmx:
        assert 'hx-swap-oob="outerHTML"' in response.text


def test_profile_create_edit_and_preserve_reviews(client, dashboard_db):
    dashboard_db.execute("INSERT INTO reviews(posting_id,action,note) VALUES (1,'later','Keep this')")
    dashboard_db.execute('DELETE FROM matches')
    dashboard_db.execute('DELETE FROM profile_sections')
    dashboard_db.execute('DELETE FROM profile')
    response = client.get('/')
    assert 'Create your profile' in response.text
    assert client.get('/filters', follow_redirects=False).headers['location'] == '/profile'
    assert client.get('/profile').status_code == 200
    response = client.post('/profile', data={
        'profile_text': 'Python developer looking for backend roles.',
        'countries': ' Albania, Germany ', 'remote_regions': 'Europe, worldwide',
    })
    assert response.status_code == 200 and 'Your profile is saved.' in response.text
    profile_id, text, filters = dashboard_db.execute('SELECT id,text,filters FROM profile').fetchone()
    assert text == '## Background\nPython developer looking for backend roles.'
    assert filters['countries'] == ['Albania', 'Germany']
    assert dashboard_db.execute('SELECT name,text FROM profile_sections WHERE profile_id=%s', (profile_id,)).fetchall() == [
        ('Background', 'Python developer looking for backend roles.'),
    ]
    assert 'Your profile is ready for matching.' in client.get('/').text
    client.post('/profile', data={'profile_text': text, 'countries': 'Albania, Germany', 'remote_regions': 'Europe, worldwide'})
    assert dashboard_db.execute('SELECT count(*) FROM profile').fetchone() == (1,)
    response = client.post('/profile', data={'profile_text': '## Engineering\nPython and SQL\n## Goals\nBackend roles', 'countries': 'Germany'})
    assert response.status_code == 200
    assert dashboard_db.execute('SELECT count(*) FROM profile').fetchone() == (2,)
    assert dashboard_db.execute('SELECT count(*) FROM matches').fetchone() == (0,)
    assert dashboard_db.execute('SELECT action,note FROM reviews WHERE posting_id=1').fetchone() == ('later', 'Keep this')


@pytest.mark.parametrize('data,message', [
    ({'profile_text': '', 'countries': 'Germany'}, 'Enter your profile'),
    ({'profile_text': 'Python developer'}, 'Add at least one country'),
    ({'profile_text': '## Empty', 'countries': 'Germany'}, 'Give each profile section'),
])
def test_profile_validation_preserves_input(client, dashboard_db, data, message):
    before = dashboard_db.execute('SELECT count(*) FROM profile').fetchone()
    response = client.post('/profile', data=data)
    assert response.status_code == 422 and message in response.text
    assert dashboard_db.execute('SELECT count(*) FROM profile').fetchone() == before
    assert 'value="Germany"' in response.text if data.get('countries') else 'Python developer' in response.text


def test_queue_search_filters_and_review_preserves_state(client, dashboard_db):
    dashboard_db.execute("UPDATE postings SET remote=true,source='remoteok',title='Python Engineer' WHERE id=1")
    dashboard_db.execute("UPDATE reviews SET action='later' WHERE posting_id=1")
    for query in ('q=python+acme', 'source=remoteok', 'seniority=mid', 'employment=full_time', 'remote=1'):
        html = client.get('/?' + query).text
        assert 'id="posting-1"' in html and 'id="posting-2"' not in html and 'id="posting-3"' not in html
    for htmx in (False, True):
        response = client.post('/reviews/1', data={
            'action': 'later', 'q': 'Python', 'source': 'remoteok', 'remote': '1', 'sort': 'title',
        }, headers={'HX-Request': 'true'} if htmx else {})
        assert 'id="posting-1"' in response.text and 'id="posting-2"' not in response.text
        assert 'name="source" value="remoteok"' in response.text
    html = client.get('/?saved=1').text
    assert 'id="posting-1"' in html and 'id="posting-2"' not in html
    assert 'No roles match these filters.' in client.get('/?q=no-such-role').text
    assert 'id="posting-1"' in client.get('/').text


@pytest.mark.parametrize('sort,expected', [('company', [3,2,1]), ('title', [2,1,3]), ('newest', [2,3,1])])
def test_additional_sort_orders(client, dashboard_db, sort, expected):
    dashboard_db.execute("""
        UPDATE postings SET company='Zulu',title='Beta',posted_at=now()-interval '3 days' WHERE id=1;
        UPDATE postings SET company='Middle',title='Alpha',posted_at=now()-interval '1 day' WHERE id=2;
        UPDATE postings SET company='Acme',title='Gamma',posted_at=now()-interval '2 days' WHERE id=3;
    """)
    html = client.get('/?sort=' + sort).text
    positions = [html.index(f'id="posting-{id}"') for id in expected]
    assert positions == sorted(positions)
    assert f'value="{sort}" selected' in html


def test_health_page_shows_latest_failed_source(client, dashboard_db, monkeypatch, tmp_path):
    dashboard_db.execute("""
        CREATE TEMP TABLE source_runs (
            id serial, source text, started_at timestamptz, finished_at timestamptz,
            status text, fetched int, error text
        );
        INSERT INTO source_runs(source, started_at, finished_at, status, fetched, error)
        VALUES ('broken', '2026-10-25 10:00+00', '2026-10-25 10:01+00', 'ok', 20, NULL),
               ('broken', '2026-10-26 12:00+02', '2026-10-26 12:01+02', 'error', 0, '<unavailable>');
    """)
    monkeypatch.setattr(health, 'connect', lambda: nullcontext(dashboard_db))
    monkeypatch.setattr(health.duapune, 'IMPORT_PATH', tmp_path / 'missing.json')
    response = client.get('/health')
    assert response.status_code == 200
    assert response.text.count('<h3>broken</h3>') == 1
    assert 'Status: Failed' in response.text
    assert '2026-10-26 10:01:00 UTC' in response.text
    assert 'Postings yielded: 0' in response.text
    assert '&lt;unavailable&gt;' in response.text
    assert 'Duapune import' in response.text and 'Missing' in response.text


def test_workspace_exposes_stored_evidence_and_preserves_view_controls(client, dashboard_db):
    from bs4 import BeautifulSoup

    dashboard_db.execute("UPDATE posting_analysis SET evidence=%s WHERE posting_id=1", (
        Jsonb({'seniority': 'We are looking for a mid-level engineer.'}),
    ))
    page = BeautifulSoup(client.get('/?hide_senior=1&hide_contract=1').text, 'html.parser')
    assert len(page.select('.index-row')) == len(page.select('.opportunity-detail')) == 2
    panel = page.select_one('#posting-1')
    assert panel.select_one('.evidence-body blockquote').text == 'Python'
    assert 'We are looking for a mid-level engineer.' in panel.text
    assert 'not proof that you lack the skill' in panel.text
    assert 'not a hiring probability' in panel.text
    for name in ('hide_senior', 'hide_contract'):
        assert page.select_one(f'#view-controls input[name="{name}"]').has_attr('checked')
        assert panel.select_one(f'input[name="{name}"]').get('value') == '1'
    assert not page.select('script[src^="http"]')


def test_workspace_browser(client, dashboard_db, monkeypatch):
    # Optional browser executable uses an existing Playwright environment, never adds a project dependency.
    import socket
    import subprocess
    import threading
    import time
    import uvicorn

    browser_python = os.environ.get('JAGENT_BROWSER_PYTHON')
    if not browser_python:
        pytest.skip('Set JAGENT_BROWSER_PYTHON to a Python with Playwright and Chromium installed')
    # Exercise wrapping with realistic headings; writes remain confined to this test's temporary tables.
    dashboard_db.execute("""
        UPDATE postings SET
          title = CASE id
            WHEN 1 THEN 'Machine Learning Engineer — Retrieval & Evaluation'
            WHEN 2 THEN 'Backend Engineer, Developer Experience & Cloud Platforms'
            ELSE 'Python Software Engineer — Data Integrations' END,
          company = CASE id WHEN 2 THEN 'European Research & Engineering Collective' ELSE 'Acme Engineering' END;
    """)
    dashboard_db.execute("""
        INSERT INTO postings(id,source,source_id,title,company,locations,first_seen,expires_at,url)
        VALUES(4,'sample','expired','Expired role','Acme','{Albania}',now(),now()-interval '1 day','https://example.com/job');
        INSERT INTO matches(posting_id,profile_id,similarity,percentile,queued)
        VALUES(4,1,0.6,100,true);
        INSERT INTO pipeline_runs(started_at,finished_at,outcome,stages)
        VALUES(now(),now(),'degraded','{"collection":{"outcome":"degraded","message":"One source timed out"}}');
    """)
    monkeypatch.setattr(dashboard, 'latest_source_runs', lambda: [])
    monkeypatch.setattr(dashboard, 'duapune_freshness', lambda: 'Missing (test fixture)')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(32)
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(dashboard.app, log_level='error'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            assert server.started
            result = subprocess.run([
                browser_python, str(Path(__file__).with_name('workspace_browser.py')),
                f'http://127.0.0.1:{port}',
            ], capture_output=True, text=True, timeout=100)
            print(result.stdout)
            assert result.returncode == 0, result.stdout + result.stderr
        finally:
            server.should_exit = True
            thread.join(timeout=10)


def test_browser_profile_line_endings_keep_cached_matches(client, dashboard_db):
    filters = dict.fromkeys(dashboard.FILTER_KEYS, []) | {'countries': ['albania']}
    dashboard_db.execute('UPDATE profile SET filters=%s WHERE id=1', (Jsonb(filters),))
    text, = dashboard_db.execute('SELECT text FROM profile WHERE id=1').fetchone()
    response = client.post('/profile', data={
        'profile_text': text.replace('\n', '\r\n'), 'countries': 'albania',
    })
    assert response.status_code == 200
    assert dashboard_db.execute('SELECT count(*) FROM profile').fetchone() == (1,)
    assert dashboard_db.execute('SELECT count(*) FROM matches WHERE profile_id=1').fetchone() == (3,)


@pytest.mark.parametrize('expiry_delta,posted_delta,first_delta,expected', [
    (-1, None, 0, False), (1, -60 * 86400, 0, True), (0, None, 0, False),
    (None, -29 * 86400, 0, True), (None, -31 * 86400, 0, False),
    (None, -30 * 86400, 0, True), (None, -30 * 86400 - 1, 0, False),
    (None, 1, 0, False), (None, None, -29 * 86400, True),
    (None, None, -31 * 86400, False), (None, None, None, False),
])
def test_queue_rechecks_canonical_activity_and_counts(dashboard_db, expiry_delta, posted_delta,
                                                     first_delta, expected):
    now = datetime(2026, 11, 3, 12, tzinfo=UTC)
    at = lambda delta: None if delta is None else now + timedelta(seconds=delta)
    dashboard_db.execute('UPDATE postings SET expires_at=%s,posted_at=%s,first_seen=%s WHERE id=1',
                         (at(expiry_delta), at(posted_delta), at(first_delta)))
    dashboard_db.execute('UPDATE postings SET first_seen=%s WHERE id IN (2,3)', (now,))
    context = dashboard.queue_context({}, now=now)
    ids = [posting['id'] for posting in context['postings']]
    assert (1 in ids) == expected
    assert context['total'] == len(ids) == (3 if expected else 2)
    # Reads never delete or rewrite stored matching/review history.
    assert dashboard_db.execute('SELECT queued FROM matches WHERE posting_id=1').fetchone() == (True,)
    assert dashboard_db.execute('SELECT count(*) FROM postings').fetchone() == (3,)


def test_inactive_saved_and_applied_history_remains_accessible(client, dashboard_db):
    client.post('/reviews/1', data={'action': 'later', 'note': 'Keep this role'})
    client.post('/reviews/2', data={'action': 'apply', 'note': 'Application sent'})
    dashboard_db.execute("UPDATE postings SET expires_at=now()-interval '1 day' WHERE id IN (1,2)")
    dashboard_db.execute('UPDATE matches SET queued=false WHERE posting_id=1')
    default = client.get('/')
    assert 'id="index-1"' not in default.text and 'id="index-2"' not in default.text
    assert 'id="index-3"' in default.text and '<strong>1</strong> shown' in default.text
    saved = client.get('/?saved=1')
    assert saved.status_code == 200 and 'id="posting-1"' in saved.text
    assert '/ 1 saved</span>' in saved.text and '/ 1 in queue</span>' not in saved.text
    assert 'Saved · inactive' in saved.text and 'recorded deadline has passed' in saved.text
    assert 'availability on the original site is not verified' in saved.text
    assert 'Keep this role' in saved.text
    assert 'Application sent' in client.get('/applied').text
    assert dashboard_db.execute('SELECT count(*) FROM reviews').fetchone() == (2,)
    # Explicit decisions on a historical saved posting continue to persist and return correct fragments.
    changed = client.post('/reviews/1', data={'action': 'later', 'saved': '1', 'note': 'Updated history'},
                          headers={'HX-Request': 'true'})
    assert changed.status_code == 200 and 'Updated history' in changed.text
    assert 'id="posting-1"' in changed.text


def test_degraded_pipeline_remains_visible_in_dashboard_and_fragments(client, dashboard_db, monkeypatch):
    monkeypatch.setattr(dashboard, "latest_source_runs", lambda: [])
    dashboard_db.execute("""
        INSERT INTO pipeline_runs(started_at,finished_at,outcome,stages)
        VALUES(now(),now(),'degraded','{"collection":{"outcome":"degraded","message":"1 source timed out"}}')
    """)
    for headers in ({}, {'HX-Request': 'true'}):
        html = client.get('/', headers=headers).text
        assert 'Latest daily pipeline: degraded' in html
    html = client.get('/health').text
    assert 'degraded' in html and '1 source timed out' in html
    assert 'Last successful import' in html and 'received timestamp is not recorded' in html
