import sqlite3

import pytest

from ydl_server.db import Job, JobsDB
from ydl_server.ydlhandler import NOT_YET_AVAILABLE_RE


@pytest.mark.parametrize("message", [
    "ERROR: [youtube] abc123: This live event will begin in 2 hours.",
    "ERROR: [youtube] abc123: Premieres in 3 hours",
    "ERROR: [youtube] abc123: Premiere in 45 minutes",
    "This live event will begin in 12 hours.",
])
def test_not_yet_available_regex_matches_known_yt_dlp_messages(message):
    assert NOT_YET_AVAILABLE_RE.search(message)


@pytest.mark.parametrize("message", [
    "ERROR: [youtube] abc123: Video unavailable",
    "ERROR: [youtube] abc123: This video is private",
    "ERROR: Unable to download webpage: HTTP Error 404",
])
def test_not_yet_available_regex_does_not_match_unrelated_errors(message):
    assert not NOT_YET_AVAILABLE_RE.search(message)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    JobsDB.create(connection)
    yield connection
    connection.close()


class _FakeCursorDB:
    """Minimal shim so we can call JobsDB instance methods against an
    arbitrary in-memory connection without going through app_config's
    real (temp-dir) metadata_db_path.
    """
    def __init__(self, conn):
        self.conn = conn


def test_get_failed_jobs_for_auto_retry_returns_only_marked_jobs(conn):
    db = _FakeCursorDB(conn)

    marked = Job("Marked", Job.FAILED, "", 0, "video/best", ["https://x/1"], extra_params={"not_yet_available": True, "auto_retry_count": 2})
    unmarked = Job("Unmarked", Job.FAILED, "", 0, "video/best", ["https://x/2"])
    completed = Job("Done", Job.COMPLETED, "", 0, "video/best", ["https://x/3"], extra_params={"not_yet_available": True})

    JobsDB.insert_job(db, marked)
    JobsDB.insert_job(db, unmarked)
    JobsDB.insert_job(db, completed)

    results = JobsDB.get_failed_jobs_for_auto_retry(db)
    names = {r["name"] for r in results}
    assert names == {"Marked"}
    assert results[0]["extra_params"]["auto_retry_count"] == 2
    assert "last_update" in results[0]
