import sqlite3

import pytest

from ydl_server.db import JobsDB


def _columns(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info('jobs')")
    columns = [row[1] for row in cursor.fetchall()]
    cursor.close()
    return columns


def _user_version(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version;")
    version = cursor.fetchone()[0]
    cursor.close()
    return version


def _index_columns(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA index_list('jobs')")
    indexed = set()
    for row in cursor.fetchall():
        cursor.execute(f"PRAGMA index_info('{row[1]}')")
        indexed.update(col[2] for col in cursor.fetchall())
    cursor.close()
    return indexed


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_db_version_no_table_returns_minus_one(conn):
    assert JobsDB.db_version(conn) == -1


def test_migrate_from_no_table_creates_full_schema(conn):
    JobsDB.migrate(conn, JobsDB.db_version(conn))
    columns = set(_columns(conn))
    assert {
        "id", "name", "status", "log", "format", "last_update", "type",
        "url", "pid", "force_generic_extractor", "extra_params",
    }.issubset(columns)
    assert _user_version(conn) == JobsDB.SCHEMA_VERSION


def _create_legacy_v0_table(conn, with_force_generic_extractor=False):
    cursor = conn.cursor()
    columns_sql = """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        status INTEGER NOT NULL,
        format TEXT,
        log TEXT,
        last_update DATETIME DEFAULT CURRENT_TIMESTAMP,
        type INTEGER NOT NULL,
        url TEXT,
        pid INTEGER
    """
    if with_force_generic_extractor:
        columns_sql += ", force_generic_extractor INTEGER DEFAULT 0"
    cursor.execute(f"CREATE TABLE jobs ({columns_sql});")
    cursor.execute("PRAGMA user_version = 0;")
    conn.commit()
    cursor.close()


def test_migrate_v0_adds_force_generic_extractor_column(conn):
    _create_legacy_v0_table(conn, with_force_generic_extractor=False)
    JobsDB.migrate(conn, JobsDB.db_version(conn))
    columns = _columns(conn)
    assert "force_generic_extractor" in columns
    assert _user_version(conn) == JobsDB.SCHEMA_VERSION


def test_migrate_v0_with_unexpected_columns_drops_and_recreates(conn):
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, some_other_column TEXT);")
    cursor.execute("PRAGMA user_version = 0;")
    conn.commit()
    cursor.close()

    JobsDB.migrate(conn, JobsDB.db_version(conn))
    columns = set(_columns(conn))
    assert "some_other_column" not in columns
    assert "extra_params" in columns
    assert _user_version(conn) == JobsDB.SCHEMA_VERSION


def _create_legacy_v1_table(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status INTEGER NOT NULL,
            format TEXT,
            log TEXT,
            last_update DATETIME DEFAULT CURRENT_TIMESTAMP,
            type INTEGER NOT NULL,
            url TEXT,
            pid INTEGER,
            force_generic_extractor INTEGER DEFAULT 0
        );
        """
    )
    cursor.execute("PRAGMA user_version = 1;")
    conn.commit()
    cursor.close()


def test_migrate_v1_adds_extra_params_column(conn):
    _create_legacy_v1_table(conn)
    JobsDB.migrate(conn, JobsDB.db_version(conn))
    assert "extra_params" in _columns(conn)
    assert _user_version(conn) == JobsDB.SCHEMA_VERSION


def _create_legacy_v2_table(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status INTEGER NOT NULL,
            format TEXT,
            log TEXT,
            last_update DATETIME DEFAULT CURRENT_TIMESTAMP,
            type INTEGER NOT NULL,
            url TEXT,
            pid INTEGER,
            force_generic_extractor INTEGER DEFAULT 0
        );
        """
    )
    cursor.execute("PRAGMA user_version = 2;")
    conn.commit()
    cursor.close()


def test_migrate_v2_adds_extra_params_column(conn):
    _create_legacy_v2_table(conn)
    JobsDB.migrate(conn, JobsDB.db_version(conn))
    assert "extra_params" in _columns(conn)
    assert _user_version(conn) == JobsDB.SCHEMA_VERSION


def test_migrate_current_version_is_a_noop_bump(conn):
    JobsDB.create(conn)
    # create() already stamps SCHEMA_VERSION; migrating again should not error
    JobsDB.migrate(conn, JobsDB.db_version(conn))
    assert _user_version(conn) == JobsDB.SCHEMA_VERSION


def test_migrate_unknown_future_version_with_compatible_schema_just_bumps_version(conn):
    JobsDB.create(conn)
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version = 999;")
    conn.commit()
    cursor.close()

    JobsDB.migrate(conn, 999)
    assert _user_version(conn) == JobsDB.SCHEMA_VERSION
    # data-preserving: table wasn't dropped/recreated
    assert set(_columns(conn)) >= {"id", "name", "extra_params"}


def test_migrate_unknown_version_with_incompatible_schema_recreates_table(conn):
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, name TEXT);")
    cursor.execute("PRAGMA user_version = 999;")
    conn.commit()
    cursor.close()

    JobsDB.migrate(conn, 999)
    columns = set(_columns(conn))
    assert {"force_generic_extractor", "extra_params", "pid"}.issubset(columns)
    assert _user_version(conn) == JobsDB.SCHEMA_VERSION


def test_create_is_idempotent(conn):
    JobsDB.create(conn)
    JobsDB.create(conn)  # "IF NOT EXISTS" — should not raise
    assert _user_version(conn) == JobsDB.SCHEMA_VERSION


def test_create_adds_status_and_last_update_indexes(conn):
    JobsDB.create(conn)
    indexed = _index_columns(conn)
    assert "status" in indexed
    assert "last_update" in indexed


def test_migrate_from_legacy_version_also_adds_indexes(conn):
    _create_legacy_v0_table(conn, with_force_generic_extractor=False)
    JobsDB.migrate(conn, JobsDB.db_version(conn))
    indexed = _index_columns(conn)
    assert "status" in indexed
    assert "last_update" in indexed
