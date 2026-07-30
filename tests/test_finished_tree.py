import os

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from ydl_server.config import get_finished_path
from ydl_server.routes import routes
from ydl_server.views import build_finished_tree


@pytest.fixture
def client():
    app = Starlette(routes=routes)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def nested_dir():
    root = get_finished_path()
    subdir = os.path.join(root, "MyShow")
    os.makedirs(subdir, exist_ok=True)
    with open(os.path.join(subdir, "episode1.mp4"), "wb") as f:
        f.write(b"data")
    nested = os.path.join(subdir, "extras")
    os.makedirs(nested, exist_ok=True)
    with open(os.path.join(nested, "behind_the_scenes.mp4"), "wb") as f:
        f.write(b"data")
    yield "MyShow"
    import shutil
    shutil.rmtree(subdir, ignore_errors=True)


def test_build_finished_tree_default_depth_marks_nested_dirs_unloaded(nested_dir):
    root = get_finished_path()
    tree = build_finished_tree(root)
    show = next(f for f in tree if f["name"] == "MyShow")
    assert show["directory"] is True
    assert show["children"] is None


def test_api_finished_top_level_does_not_eagerly_load_children(client, nested_dir):
    resp = client.get("/api/finished")
    assert resp.status_code == 200
    body = resp.json()
    show = next(f for f in body if f["name"] == "MyShow")
    assert show["children"] is None


def test_api_finished_with_path_returns_one_level_of_that_directory(client, nested_dir):
    resp = client.get("/api/finished?path=MyShow")
    assert resp.status_code == 200
    body = resp.json()
    names = {f["name"] for f in body}
    assert names == {"episode1.mp4", "extras"}
    extras = next(f for f in body if f["name"] == "extras")
    assert extras["directory"] is True
    assert extras["children"] is None  # still lazy - one more level to expand


def test_api_finished_path_rejects_traversal(client, nested_dir):
    resp = client.get("/api/finished?path=%2e%2e")
    assert resp.status_code == 400
    assert resp.json()["success"] is False


def test_api_finished_path_rejects_nonexistent_directory(client):
    resp = client.get("/api/finished?path=does-not-exist")
    assert resp.status_code == 400
    assert resp.json()["success"] is False


def test_api_finished_path_rejects_a_file_path(client, nested_dir):
    resp = client.get("/api/finished?path=MyShow/episode1.mp4")
    assert resp.status_code == 400
    assert resp.json()["success"] is False
