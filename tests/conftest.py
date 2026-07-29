"""
ydl_server.config loads and validates its configuration at *import time*
(module-level `app_config = load_config()` + `get_finished_path()`), so a
valid config file must exist before ydl_server.config (or anything that
imports it, which is nearly every module in the package) is imported for
the first time in the process.

This conftest sets YDL_CONFIG_PATH to a throwaway config in a temp
directory before test collection imports any test module, so that
first import is safe and isolated from the real config.yml / any real
download directory.
"""
import os
import tempfile

import yaml

_tmp_dir = tempfile.mkdtemp(prefix="ydl-server-tests-")
_downloads_dir = os.path.join(_tmp_dir, "downloads")
os.makedirs(_downloads_dir, exist_ok=True)

_test_config = {
    "ydl_server": {
        "port": 8080,
        "host": "0.0.0.0",
        "debug": False,
        "metadata_db_path": os.path.join(_tmp_dir, ".ydl-metadata.db"),
        "output_playlist": os.path.join(
            _downloads_dir, "%(playlist_title)s [%(playlist_id)s]", "%(title)s.%(ext)s"
        ),
        "max_log_entries": 100,
        "default_format": "video/best",
        "download_workers_count": 2,
    },
    "ydl_options": {
        "output": os.path.join(_downloads_dir, "%(title)s [%(id)s].%(ext)s"),
        "cache-dir": os.path.join(_tmp_dir, ".cache"),
        "ignore-errors": True,
    },
    "aliases": {},
    "profiles": {},
}

_config_path = os.path.join(_tmp_dir, "config.yml")
with open(_config_path, "w") as f:
    yaml.safe_dump(_test_config, f)

os.environ["YDL_CONFIG_PATH"] = _config_path

TEST_TMP_DIR = _tmp_dir
TEST_DOWNLOADS_DIR = _downloads_dir
