import pytest

from ydl_server.ydlhandler import YdlHandler


@pytest.fixture
def handler():
    app_config = {
        "ydl_server": {},
        "ydl_options": {"output": "/data/%(title)s.%(ext)s"},
        "download_folders": ["Movies", "TV Shows"],
    }
    return YdlHandler(app_config, jobshandler=None)


def test_get_format_and_profile_parses_folder_token(handler):
    _, _, _, _, folder = handler.get_format_and_profile("video/best,folder/Movies")
    assert folder == "folder/Movies"


def test_get_format_and_profile_no_folder_token_returns_none(handler):
    _, _, _, _, folder = handler.get_format_and_profile("video/best")
    assert folder is None


def test_get_folder_returns_configured_folder_name(handler):
    assert handler.get_folder("folder/Movies") == "Movies"


def test_get_folder_none_input_returns_none(handler):
    assert handler.get_folder(None) is None


def test_get_folder_unknown_folder_raises(handler):
    with pytest.raises(Exception, match="Unknown download folder"):
        handler.get_folder("folder/Nope")


def test_get_folder_no_configured_folders_raises():
    app_config = {"ydl_server": {}, "ydl_options": {}}
    handler = YdlHandler(app_config, jobshandler=None)
    with pytest.raises(Exception, match="Unknown download folder"):
        handler.get_folder("folder/Movies")


def test_get_ydl_options_returns_resolved_folder(handler):
    ydl_opts, folder = handler.get_ydl_options(
        handler.app_config["ydl_options"], {"format": "video/best,folder/Movies"}
    )
    assert folder == "Movies"
    assert ydl_opts["output"] == "/data/%(title)s.%(ext)s"  # unchanged here - download() applies it


def test_get_ydl_options_no_folder_returns_none(handler):
    _, folder = handler.get_ydl_options(
        handler.app_config["ydl_options"], {"format": "video/best"}
    )
    assert folder is None
