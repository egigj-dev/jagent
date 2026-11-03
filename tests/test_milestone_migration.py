# Integration migration checks; a unique test schema proves additive DDL, repeatability and preservation of existing data.
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from jagent.db import connect

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'deploy/milestone-a.sql'


def test_release_migration_matches_canonical_schema():
    schema = (ROOT / 'schema.sql').read_text()
    start = schema.index('CREATE TABLE IF NOT EXISTS pipeline_runs (')
    assert schema[start:schema.index(';', start) + 1] in MIGRATION.read_text()
    assert MIGRATION.read_text().count('CREATE TABLE') == 1
    assert 'lock_timeout' in MIGRATION.read_text()


def test_additive_migration_is_repeatable_and_preserves_history():
    if os.environ.get('JAGENT_TEST_POSTGRES') != '1':
        pytest.skip('Set JAGENT_TEST_POSTGRES=1 to exercise the migration in a private test schema')
    name = 'integration_' + uuid4().hex
    with connect() as connection:
        assert connection.execute('SELECT current_database()').fetchone()[0].endswith('_test')
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
        connection.commit()
        try:
            connection.execute(sql.SQL('SET search_path TO {},public').format(sql.Identifier(name)))
            old_schema = (ROOT / 'schema.sql').read_text().split('-- Daily run verdicts;')[0]
            connection.execute(old_schema)
            connection.execute("""
                INSERT INTO postings(id,source,source_id,title) VALUES(1,'sample','1','Engineer');
                INSERT INTO profile(id,text,filters) VALUES(1,'Preserved profile','{}');
                INSERT INTO matches(posting_id,profile_id,similarity,queued) VALUES(1,1,0.7,true);
                INSERT INTO reviews(posting_id,action,note) VALUES(1,'apply','Preserved note');
            """)
            connection.commit()
            for _ in range(2):
                connection.execute(MIGRATION.read_text())
            assert connection.execute('SELECT count(*) FROM postings').fetchone() == (1,)
            assert connection.execute('SELECT text FROM profile').fetchone() == ('Preserved profile',)
            assert connection.execute('SELECT similarity,queued FROM matches').fetchone() == (0.7, True)
            assert connection.execute('SELECT action,note FROM reviews').fetchone() == ('apply', 'Preserved note')
            stages = {'collection': {'outcome': 'success', 'usable_sources': 2}}
            for outcome in ('success', 'degraded', 'failed', None):
                connection.execute('INSERT INTO pipeline_runs(started_at,outcome,stages) VALUES(now(),%s,%s)',
                                   (outcome, Jsonb(stages)))
            assert connection.execute('SELECT count(*) FROM pipeline_runs').fetchone() == (4,)
            assert connection.execute('SELECT stages FROM pipeline_runs LIMIT 1').fetchone() == (stages,)
            with pytest.raises(psycopg.errors.CheckViolation):
                with connection.transaction():
                    connection.execute("INSERT INTO pipeline_runs(started_at,outcome) VALUES(now(),'invalid')")
            connection.commit()
            # Rollback to the previous app leaves the additive history table and all old tables intact.
            assert connection.execute('SELECT note FROM reviews').fetchone() == ('Preserved note',)
        finally:
            connection.rollback()
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
            connection.commit()
