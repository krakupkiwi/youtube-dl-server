import pytest

from ydl_server import config as config_module
from ydl_server.config import (
    is_valid_download_folder_name,
    is_valid_download_folder_path,
    set_age_limit,
    set_download_folders,
)

SAMPLE_CONFIG = """\
ydl_server:   # youtube-dl-server specific settings
  port: 8080

ydl_options:  # youtube-dl options
  output: '/x/%(title)s.%(ext)s' # output template
  ignore-errors: True # skip errors
"""

SAMPLE_CONFIG_WITH_AGE_LIMIT = """\
ydl_server:
  port: 8080

ydl_options:
  output: '/x/%(title)s.%(ext)s'
  age-limit: 13
  ignore-errors: True
"""

SAMPLE_CONFIG_WITH_DOWNLOAD_FOLDERS = """\
ydl_server:
  port: 8080

ydl_options:
  output: '/x/%(title)s.%(ext)s'
  ignore-errors: True

download_folders:  # subfolders selectable as a download destination
  - Movies
  - TV Shows

aliases:
  mp3:
      name: 'MP3 audio'
"""


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yml"
    config_file.write_text(SAMPLE_CONFIG)
    monkeypatch.setenv("YDL_CONFIG_PATH", str(config_file))

    original_age_limit = config_module.app_config["ydl_options"].get("age-limit")
    original_download_folders = config_module.app_config.get("download_folders")
    yield config_file
    if original_age_limit is None:
        config_module.app_config["ydl_options"].pop("age-limit", None)
    else:
        config_module.app_config["ydl_options"]["age-limit"] = original_age_limit
    if original_download_folders is None:
        config_module.app_config.pop("download_folders", None)
    else:
        config_module.app_config["download_folders"] = original_download_folders


def test_set_age_limit_inserts_new_line_preserving_comments(isolated_config):
    set_age_limit(18)

    text = isolated_config.read_text()
    assert "age-limit: 18" in text
    assert "# output template" in text
    assert config_module.app_config["ydl_options"]["age-limit"] == 18


def test_set_age_limit_updates_existing_line(isolated_config):
    isolated_config.write_text(SAMPLE_CONFIG_WITH_AGE_LIMIT)

    set_age_limit(21)

    text = isolated_config.read_text()
    assert "age-limit: 21" in text
    assert "age-limit: 13" not in text
    assert config_module.app_config["ydl_options"]["age-limit"] == 21


def test_set_age_limit_none_removes_existing_line(isolated_config):
    isolated_config.write_text(SAMPLE_CONFIG_WITH_AGE_LIMIT)

    set_age_limit(None)

    text = isolated_config.read_text()
    assert "age-limit" not in text
    assert "output:" in text
    assert "ignore-errors: True" in text
    assert "age-limit" not in config_module.app_config["ydl_options"]


def test_set_age_limit_none_when_absent_is_a_noop(isolated_config):
    set_age_limit(None)

    text = isolated_config.read_text()
    assert text == SAMPLE_CONFIG
    assert "age-limit" not in config_module.app_config["ydl_options"]


# --- is_valid_download_folder_name -----------------------------------------

@pytest.mark.parametrize("name", ["Movies", "TV Shows", "Kids_2024", "Misc (temp)"])
def test_is_valid_download_folder_name_accepts_plain_names(name):
    assert is_valid_download_folder_name(name) is True


@pytest.mark.parametrize(
    "name", ["", ".", "..", "Movies/Action", "Movies\\Action", "a,b", "\x00"]
)
def test_is_valid_download_folder_name_rejects_unsafe_names(name):
    assert is_valid_download_folder_name(name) is False


# --- is_valid_download_folder_path ------------------------------------------

@pytest.mark.parametrize(
    "path",
    ["/concerts", "/mnt/user/Movies", "/a/b/c", "C:\\Users\\foo\\Concerts", "C:/Users/foo/Concerts"],
)
def test_is_valid_download_folder_path_accepts_absolute_paths(path):
    assert is_valid_download_folder_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/",
        "concerts",
        "relative/path",
        "/concerts/../etc",
        "/a/..",
        "\x00",
        None,
        "C:\\",
        "C:/",
        "C:\\..\\etc",
    ],
)
def test_is_valid_download_folder_path_rejects_unsafe_paths(path):
    assert is_valid_download_folder_path(path) is False


# --- set_download_folders ---------------------------------------------------

def test_set_download_folders_inserts_new_block(isolated_config):
    set_download_folders(["Movies", "TV Shows"])

    text = isolated_config.read_text()
    assert "download_folders:" in text
    assert "  - 'Movies'" in text
    assert "  - 'TV Shows'" in text
    assert "# output template" in text
    assert config_module.app_config["download_folders"] == [
        {"name": "Movies", "path": None},
        {"name": "TV Shows", "path": None},
    ]


def test_set_download_folders_replaces_existing_block_preserving_rest(isolated_config):
    isolated_config.write_text(SAMPLE_CONFIG_WITH_DOWNLOAD_FOLDERS)

    set_download_folders(["Music"])

    text = isolated_config.read_text()
    assert "  - 'Music'" in text
    assert "Movies" not in text
    assert "TV Shows" not in text
    assert "aliases:" in text
    assert "mp3:" in text
    assert config_module.app_config["download_folders"] == [{"name": "Music", "path": None}]


def test_set_download_folders_empty_list_removes_block(isolated_config):
    isolated_config.write_text(SAMPLE_CONFIG_WITH_DOWNLOAD_FOLDERS)

    set_download_folders([])

    text = isolated_config.read_text()
    assert "download_folders" not in text
    assert "aliases:" in text
    assert config_module.app_config["download_folders"] == []


def test_set_download_folders_empty_when_absent_is_a_noop(isolated_config):
    set_download_folders([])

    text = isolated_config.read_text()
    assert text == SAMPLE_CONFIG
    assert config_module.app_config["download_folders"] == []


def test_set_download_folders_with_explicit_path(isolated_config):
    set_download_folders([{"name": "Concerts", "path": "/concerts"}])

    text = isolated_config.read_text()
    assert "  - name: 'Concerts'" in text
    assert "    path: '/concerts'" in text
    assert config_module.app_config["download_folders"] == [
        {"name": "Concerts", "path": "/concerts"}
    ]


def test_set_download_folders_mixed_entries_round_trip(isolated_config):
    set_download_folders(["Movies", {"name": "Concerts", "path": "/concerts"}])

    text = isolated_config.read_text()
    assert "  - 'Movies'" in text
    assert "  - name: 'Concerts'" in text
    assert "    path: '/concerts'" in text

    # Re-reading the file the way load_config() would should normalize both
    # shapes identically to what we just wrote.
    import yaml
    from ydl_server.config import normalize_download_folders

    reloaded = yaml.safe_load(text)
    normalize_download_folders(reloaded)
    assert reloaded["download_folders"] == [
        {"name": "Movies", "path": None},
        {"name": "Concerts", "path": "/concerts"},
    ]


def test_set_download_folders_quotes_embedded_special_characters(isolated_config):
    set_download_folders(["It's Movies"])

    text = isolated_config.read_text()
    assert "  - 'It''s Movies'" in text
    assert config_module.app_config["download_folders"] == [
        {"name": "It's Movies", "path": None}
    ]
