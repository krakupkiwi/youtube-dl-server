from ydl_server.views import summarize_video_info


def test_summarize_single_video():
    info = {
        "_type": "video",
        "id": "abc123",
        "title": "My Video",
        "uploader": "Some Channel",
        "duration": 120,
        "is_live": False,
        "availability": "public",
        "extractor": "youtube",
        "formats": [
            {"format_id": "140", "ext": "m4a", "resolution": "audio only", "filesize": 1000},
            {"format_id": "399", "ext": "mp4", "resolution": "1920x1080", "filesize": 40000000},
        ],
    }
    summary = summarize_video_info(info)
    assert summary == {
        "is_playlist": False,
        "id": "abc123",
        "title": "My Video",
        "uploader": "Some Channel",
        "duration": 120,
        "is_live": False,
        "availability": "public",
        "extractor": "youtube",
        "best_format": {
            "format_id": "399",
            "ext": "mp4",
            "resolution": "1920x1080",
            "filesize": 40000000,
        },
    }


def test_summarize_video_with_no_formats():
    info = {"_type": "video", "id": "abc123", "title": "My Video"}
    summary = summarize_video_info(info)
    assert summary["best_format"] is None
    assert summary["is_playlist"] is False


def test_summarize_video_falls_back_to_filesize_approx():
    info = {
        "_type": "video",
        "formats": [{"format_id": "399", "ext": "mp4", "filesize_approx": 12345}],
    }
    summary = summarize_video_info(info)
    assert summary["best_format"]["filesize"] == 12345


def test_summarize_video_falls_back_to_format_note_for_resolution():
    info = {
        "_type": "video",
        "formats": [{"format_id": "140", "ext": "m4a", "format_note": "medium"}],
    }
    summary = summarize_video_info(info)
    assert summary["best_format"]["resolution"] == "medium"


def test_summarize_playlist():
    info = {
        "_type": "playlist",
        "title": "My Playlist",
        "entries": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
    }
    summary = summarize_video_info(info)
    assert summary == {
        "is_playlist": True,
        "title": "My Playlist",
        "video_count": 3,
    }


def test_summarize_playlist_with_no_entries():
    info = {"_type": "playlist", "title": "Empty Playlist"}
    summary = summarize_video_info(info)
    assert summary["video_count"] == 0
