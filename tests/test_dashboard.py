# Dashboard tests; temporary tables isolate reviews/profile versions and fake API calls forbid network use.
from contextlib import nullcontext
from datetime import UTC, datetime
import os
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from jagent import cli, dashboard
from jagent.db import connect


@pytest.fixture
def dashboard_db(monkeypatch):
    if os.environ.get("JAGENT_TEST_POSTGRES") != "1":
        pytest.skip("Set JAGENT_TEST_POSTGRES=1 to test dashboard in temporary tables")
    with connect() as connection:
        schema = (Path(__file__).resolve().parent.parent / "schema.sql").read_text()
        for name in ("postings", "profile", "profile_sections", "matches", "posting_analysis", "reviews"):
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
                    'https://example.com/job','{https://example.org/other}')
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


def test_view_toggles_default_on_and_do_not_rerank(client,dashboard_db):
    assert 'id="posting-2"' not in client.get('/').text
    assert 'id="posting-2"' in client.get('/?views=1').text
    assert dashboard_db.execute('SELECT count(*) FROM matches WHERE queued').fetchone()==(3,)


@pytest.mark.parametrize('field,value',[
    ('seniority','lead'),('required_languages',['French']),('employment_types',['equity_only']),
])
def test_each_view_filter(field,value):
    posting={"seniority":"mid","required_languages":["Italian","Albanian"],"employment_types":["full_time"]}
    assert dashboard.visible(posting,dashboard.view_options({}))
    posting[field]=value
    assert not dashboard.visible(posting,dashboard.view_options({}))
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
    today = datetime(2026, 10, 14, tzinfo=UTC).date()
    monkeypatch.setitem(dashboard.templates.env.filters, 'days_left',
                        lambda expiry: dashboard.days_left(expiry, today))
    dashboard_db.execute("""
        UPDATE postings SET source='duapune', expires_at='2026-10-17 21:59:00+00' WHERE id=1;
        UPDATE postings SET expires_at='2026-10-16 21:59:00+00' WHERE id=3;
    """)
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
