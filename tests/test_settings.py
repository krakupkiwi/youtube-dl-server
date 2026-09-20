import pytest

from ydl_server import config as config_module
from ydl_server.config import set_age_limit

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


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yml"
    config_file.write_text(SAMPLE_CONFIG)
    monkeypatch.setenv("YDL_CONFIG_PATH", str(config_file))

    original_age_limit = config_module.app_config["ydl_options"].get("age-limit")
    yield config_file
    if original_age_limit is None:
        config_module.app_config["ydl_options"].pop("age-limit", None)
    else:
        config_module.app_config["ydl_options"]["age-limit"] = original_age_limit


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
