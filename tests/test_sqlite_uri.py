from ydl_server.db import _sqlite_uri


def test_unix_absolute_path():
    assert _sqlite_uri("/data/.ydl-metadata.db") == "file:///data/.ydl-metadata.db"


def test_windows_drive_path_with_forward_slashes():
    assert _sqlite_uri("C:/Users/foo/.ydl-metadata.db") == "file:///C:/Users/foo/.ydl-metadata.db"


def test_windows_drive_path_with_backslashes():
    assert _sqlite_uri("C:\\Users\\foo\\.ydl-metadata.db") == "file:///C:/Users/foo/.ydl-metadata.db"


def test_readonly_appends_mode_ro_query_param():
    uri = _sqlite_uri("/data/.ydl-metadata.db", readonly=True)
    assert uri == "file:///data/.ydl-metadata.db?mode=ro"


def test_not_readonly_has_no_query_param():
    uri = _sqlite_uri("/data/.ydl-metadata.db", readonly=False)
    assert "?" not in uri


def test_single_letter_path_is_not_mistaken_for_a_drive():
    # len(path) <= 1 guard: shouldn't index out of range or misfire on "a"
    assert _sqlite_uri("a") == "file://a"
