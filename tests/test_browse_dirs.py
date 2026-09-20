import os

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from ydl_server.routes import routes


@pytest.fixture
def client():
    app = Starlette(routes=routes)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "Movies").mkdir()
    (tmp_path / "Music").mkdir()
    (tmp_path / "Movies" / "Action").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "not_a_dir.txt").write_text("data")
    return tmp_path


def test_browse_dirs_lists_subdirectories_only(client, tree):
    resp = client.get("/api/browse-dirs", params={"path": str(tree)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["dirs"] == ["Movies", "Music"]


def test_browse_dirs_skips_hidden_directories(client, tree):
    resp = client.get("/api/browse-dirs", params={"path": str(tree)})
    assert ".hidden" not in resp.json()["dirs"]


def test_browse_dirs_sorted_case_insensitively(client, tmp_path):
    (tmp_path / "zebra").mkdir()
    (tmp_path / "Apple").mkdir()
    (tmp_path / "banana").mkdir()

    resp = client.get("/api/browse-dirs", params={"path": str(tmp_path)})
    assert resp.json()["dirs"] == ["Apple", "banana", "zebra"]


def test_browse_dirs_reports_correct_parent(client, tree):
    resp = client.get("/api/browse-dirs", params={"path": str(tree / "Movies")})
    body = resp.json()
    assert body["success"] is True
    assert os.path.normpath(body["parent"]) == os.path.normpath(str(tree))
    assert body["dirs"] == ["Action"]


def test_browse_dirs_rejects_relative_path(client):
    resp = client.get("/api/browse-dirs", params={"path": "relative/path"})
    assert resp.status_code == 400
    assert resp.json()["success"] is False


def test_browse_dirs_rejects_nonexistent_directory(client, tmp_path):
    resp = client.get("/api/browse-dirs", params={"path": str(tmp_path / "does-not-exist")})
    assert resp.status_code == 400
    assert resp.json()["success"] is False


def test_browse_dirs_rejects_a_file_path(client, tree):
    resp = client.get("/api/browse-dirs", params={"path": str(tree / "not_a_dir.txt")})
    assert resp.status_code == 400
    assert resp.json()["success"] is False


def test_browse_dirs_defaults_to_filesystem_root(client):
    resp = client.get("/api/browse-dirs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["parent"] is None
