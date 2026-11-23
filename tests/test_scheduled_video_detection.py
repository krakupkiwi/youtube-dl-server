"""Upcoming live events / premieres are parked in the Scheduled state instead
of failing. When the extractor gives no release time, the job is re-checked
after UPCOMING_UNKNOWN_RETRY_DELAY instead of being failed outright.
"""
import io
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from ydl_server import ydlhandler
from ydl_server.db import Job


@pytest.fixture
def handler():
    with patch.object(ydlhandler.YdlHandler, "import_ydl_module"):
        h = ydlhandler.YdlHandler(
            {"ydl_server": {}, "ydl_options": {"output": "/downloads/%(title)s.%(ext)s"}},
            Mock(),
        )
    h.ydl_cmd = ["yt-dlp"]
    h.run_logged_command = Mock(side_effect=AssertionError("must not start a download"))
    return h


def make_job():
    return SimpleNamespace(
        id=1, extra_params={}, url=["https://example.com/live"], log="",
        status=Job.PENDING, force_generic_extractor=False,
    )


def test_upcoming_with_release_time_is_scheduled_for_that_time(handler):
    release = int(time.time()) + 6 * 3600
    handler.fetch_metadata = Mock(return_value=(0, [
        {"title": "Live", "live_status": "is_upcoming", "release_timestamp": release},
    ]))
    job = make_job()
    handler.download(job, {"format": "video/best"}, None)

    assert job.status == Job.SCHEDULED
    assert job.scheduled_at == release + ydlhandler.SCHEDULE_RELEASE_BUFFER


def test_upcoming_without_release_time_is_rechecked_later(handler):
    handler.fetch_metadata = Mock(return_value=(0, [
        {"title": "Live", "live_status": "is_upcoming"},
    ]))
    job = make_job()
    before = int(time.time())
    handler.download(job, {"format": "video/best"}, None)

    assert job.status == Job.SCHEDULED
    expected = before + ydlhandler.UPCOMING_UNKNOWN_RETRY_DELAY
    assert expected <= job.scheduled_at <= expected + 5
    assert job.extra_params["schedule_attempts"] == 1


def test_upcoming_is_not_scheduled_when_disabled(handler):
    handler.app_config["ydl_server"]["schedule_upcoming"] = False
    handler.fetch_metadata = Mock(return_value=(0, [
        {"title": "Live", "live_status": "is_upcoming"},
    ]))
    handler.run_logged_command = Mock(return_value=0)
    handler.run_metadata_command = Mock(return_value=(1, b"", b""))
    job = make_job()
    handler.download(job, {"format": "video/best"}, io.StringIO())

    assert job.status == Job.COMPLETED
    handler.run_logged_command.assert_called_once()
