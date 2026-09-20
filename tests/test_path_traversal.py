import os

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from ydl_server.config import (
    apply_download_folder,
    get_finished_path,
    get_static_prefix,
    insert_output_subfolder,
    resolve_finished_file,
    set_output_root,
)
from ydl_server.routes import routes


# --- get_static_prefix ---------------------------------------------------

def test_get_static_prefix_stops_at_template_variable():
    assert get_static_prefix("/data/foo/%(title)s.mp4") == "/data/foo"


def test_get_static_prefix_handles_windows_backslashes():
    assert get_static_prefix("C:\\Users\\foo\\bar\\%(title)s.mp4") == "C:/Users/foo/bar"


def test_get_static_prefix_no_static_prefix_returns_empty_string():
    # This is the upstream #152 scenario: a template with no directory
    # component at all. It must NOT resolve to "/" (filesystem root).
    assert get_static_prefix("%(title)s [%(id)s].%(ext)s") == ""


def test_get_static_prefix_root_only_template_returns_root():
    assert get_static_prefix("/%(title)s.mp4") == "/"


# --- insert_output_subfolder ----------------------------------------------

def test_insert_output_subfolder_no_folder_is_a_noop():
    template = "/data/foo/%(title)s.mp4"
    assert insert_output_subfolder(template, None) == template
    assert insert_output_subfolder(template, "") == template


def test_insert_output_subfolder_absolute_prefix():
    assert (
        insert_output_subfolder("/data/foo/%(title)s.mp4", "Movies")
        == "/data/foo/Movies/%(title)s.mp4"
    )


def test_insert_output_subfolder_root_only_prefix():
    assert (
        insert_output_subfolder("/%(title)s.mp4", "Movies") == "/Movies/%(title)s.mp4"
    )


def test_insert_output_subfolder_no_static_prefix():
    assert (
        insert_output_subfolder("%(title)s [%(id)s].%(ext)s", "Movies")
        == "Movies/%(title)s [%(id)s].%(ext)s"
    )


def test_insert_output_subfolder_relative_prefix():
    assert (
        insert_output_subfolder("youtube-dl/%(title)s.mp4", "Movies")
        == "youtube-dl/Movies/%(title)s.mp4"
    )


def test_insert_output_subfolder_playlist_template():
    template = "/data/%(playlist_title)s [%(playlist_id)s]/%(title)s.%(ext)s"
    assert (
        insert_output_subfolder(template, "Movies")
        == "/data/Movies/%(playlist_title)s [%(playlist_id)s]/%(title)s.%(ext)s"
    )


def test_insert_output_subfolder_after_title_override():
    # Mirrors what YdlHandler.download() produces for a user-supplied title
    # override before folder insertion runs: a literal filename with no
    # further "%" markers except the extension placeholder.
    template = "/data/foo/My Video.%(ext)s"
    assert (
        insert_output_subfolder(template, "Movies") == "/data/foo/Movies/My Video.%(ext)s"
    )


# --- set_output_root -------------------------------------------------------

def test_set_output_root_replaces_absolute_prefix():
    assert (
        set_output_root("/data/foo/%(title)s.mp4", "/concerts")
        == "/concerts/%(title)s.mp4"
    )


def test_set_output_root_replaces_root_only_prefix():
    assert set_output_root("/%(title)s.mp4", "/concerts") == "/concerts/%(title)s.mp4"


def test_set_output_root_no_static_prefix():
    assert (
        set_output_root("%(title)s [%(id)s].%(ext)s", "/concerts")
        == "/concerts/%(title)s [%(id)s].%(ext)s"
    )


def test_set_output_root_windows_new_root():
    assert (
        set_output_root("/data/foo/%(title)s.mp4", "C:\\Users\\foo\\Concerts")
        == "C:\\Users\\foo\\Concerts/%(title)s.mp4"
    )


def test_set_output_root_strips_trailing_slash_on_new_root():
    assert (
        set_output_root("/data/%(title)s.mp4", "/concerts/") == "/concerts/%(title)s.mp4"
    )


def test_set_output_root_playlist_template():
    template = "/data/%(playlist_title)s [%(playlist_id)s]/%(title)s.%(ext)s"
    assert (
        set_output_root(template, "/concerts")
        == "/concerts/%(playlist_title)s [%(playlist_id)s]/%(title)s.%(ext)s"
    )


# --- apply_download_folder --------------------------------------------------

def test_apply_download_folder_none_is_a_noop():
    template = "/data/foo/%(title)s.mp4"
    assert apply_download_folder(template, None) == template


def test_apply_download_folder_bare_name_nests_as_subfolder():
    assert (
        apply_download_folder("/data/foo/%(title)s.mp4", {"name": "Movies", "path": None})
        == "/data/foo/Movies/%(title)s.mp4"
    )


def test_apply_download_folder_with_path_replaces_root():
    assert (
        apply_download_folder(
            "/data/foo/%(title)s.mp4", {"name": "Concerts", "path": "/concerts"}
        )
        == "/concerts/%(title)s.mp4"
    )


# --- resolve_finished_file ------------------------------------------------

def test_resolve_finished_file_plain_name_stays_inside_root():
    root = get_finished_path()
    resolved = resolve_finished_file("video.mp4")
    assert resolved == os.path.realpath(os.path.join(root, "video.mp4"))


def test_resolve_finished_file_nested_path_stays_inside_root():
    root = get_finished_path()
    resolved = resolve_finished_file("subdir/video.mp4")
    assert resolved == os.path.realpath(os.path.join(root, "subdir", "video.mp4"))


@pytest.mark.parametrize("malicious", [
    "../outside.txt",
    "../../etc/passwd",
    "subdir/../../outside.txt",
    "..",
])
def test_resolve_finished_file_rejects_traversal_attempts(malicious):
    assert resolve_finished_file(malicious) is None


def test_resolve_finished_file_rejects_absolute_path_escape():
    # An absolute path should not be allowed to just replace the root.
    assert resolve_finished_file(os.path.abspath(os.sep)) is None


def test_resolve_finished_file_accepts_root_itself():
    root = get_finished_path()
    assert resolve_finished_file(".") == os.path.realpath(root)


# --- live endpoints: api_delete_file / api_cut_file -----------------------

@pytest.fixture
def client():
    app = Starlette(routes=routes)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_file():
    root = get_finished_path()
    path = os.path.join(root, "sample.mp4")
    with open(path, "wb") as f:
        f.write(b"fake video data")
    yield "sample.mp4"
    if os.path.exists(path):
        os.remove(path)


def test_delete_file_rejects_traversal(client):
    # %2e%2e survives client-side URL normalization (a literal ".." in the
    # path would be collapsed by httpx before the request is even sent),
    # so this actually exercises the server's own defense.
    resp = client.request("DELETE", "/api/finished/%2e%2e/outside.txt")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False


def test_delete_file_removes_a_real_file(client, sample_file):
    root = get_finished_path()
    assert os.path.exists(os.path.join(root, sample_file))
    resp = client.request("DELETE", f"/api/finished/{sample_file}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert not os.path.exists(os.path.join(root, sample_file))


def test_cut_file_rejects_backslash_in_output_name(client, sample_file):
    resp = client.post(
        f"/api/finished/{sample_file}/cut",
        json={"start": "0", "end": "10", "output": "sub\\..\\..\\evil.mp4"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Invalid output filename"


def test_cut_file_rejects_slash_in_output_name(client, sample_file):
    resp = client.post(
        f"/api/finished/{sample_file}/cut",
        json={"start": "0", "end": "10", "output": "../evil.mp4"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is False


def test_cut_file_rejects_null_byte_in_output_name(client, sample_file):
    resp = client.post(
        f"/api/finished/{sample_file}/cut",
        json={"start": "0", "end": "10", "output": "evil\x00.mp4"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is False


def test_cut_file_rejects_leading_dot_output_name(client, sample_file):
    resp = client.post(
        f"/api/finished/{sample_file}/cut",
        json={"start": "0", "end": "10", "output": ".hidden.mp4"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is False


def test_cut_file_rejects_traversal_in_source_fname(client):
    resp = client.post(
        "/api/finished/%2e%2e/outside.mp4/cut",
        json={"start": "0", "end": "10", "output": "out.mp4"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is False
