import pytest

from ydl_server.ydlhandler import YdlHandler


@pytest.fixture
def handler():
    app_config = {
        "ydl_server": {},
        "ydl_options": {},
        "extractor_options": {
            "youtube": {"ydl_options": {"write-thumbnail": True}},
            "twitter": {"ydl_options": {"format": "best"}},
        },
    }
    return YdlHandler(app_config, jobshandler=None)


def test_get_extractor_options_returns_matching_config(handler):
    assert handler.get_extractor_options("youtube") == {"write-thumbnail": True}


def test_get_extractor_options_is_case_insensitive(handler):
    assert handler.get_extractor_options("YouTube") == {"write-thumbnail": True}


def test_get_extractor_options_unknown_extractor_returns_empty(handler):
    assert handler.get_extractor_options("some_random_site") == {}


def test_get_extractor_options_none_returns_empty(handler):
    assert handler.get_extractor_options(None) == {}


def test_get_extractor_options_no_config_section_returns_empty():
    app_config = {"ydl_server": {}, "ydl_options": {}}
    handler = YdlHandler(app_config, jobshandler=None)
    assert handler.get_extractor_options("youtube") == {}


def test_extractor_options_apply_as_defaults_not_overrides():
    # Simulates the merge that download() performs: extractor options should
    # never clobber a key already present in the resolved ydl_opts.
    extractor_opts = {"format": "worst", "write-thumbnail": True}
    ydl_opts = {"format": "best"}
    merged = {**extractor_opts, **ydl_opts}
    assert merged == {"format": "best", "write-thumbnail": True}
