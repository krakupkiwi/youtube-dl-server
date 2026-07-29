import pytest

from ydl_server.config import (
    expand_alias,
    expand_uses,
    normalize_use,
    resolve_aliases,
)


def test_normalize_use_none_returns_empty_list():
    assert normalize_use(None) == []


def test_normalize_use_string_wraps_in_list():
    assert normalize_use("mp3") == ["mp3"]


def test_normalize_use_list_passthrough():
    assert normalize_use(["mp3", "thumbnails"]) == ["mp3", "thumbnails"]


def test_expand_alias_returns_own_options():
    aliases = {"mp3": {"ydl_options": {"format": "bestaudio/best"}}}
    assert expand_alias("mp3", aliases, []) == {"format": "bestaudio/best"}


def test_expand_alias_unknown_name_raises():
    with pytest.raises(Exception, match="Unknown alias"):
        expand_alias("nope", {}, [])


def test_expand_alias_direct_self_reference_raises():
    aliases = {"a": {"use": "a", "ydl_options": {}}}
    with pytest.raises(Exception, match="Recursive alias definition"):
        expand_alias("a", aliases, [])


def test_expand_alias_indirect_cycle_raises():
    aliases = {
        "a": {"use": "b", "ydl_options": {}},
        "b": {"use": "a", "ydl_options": {}},
    }
    with pytest.raises(Exception, match="Recursive alias definition"):
        expand_alias("a", aliases, [])


def test_expand_alias_composes_used_aliases_in_order():
    aliases = {
        "mp3": {"ydl_options": {"format": "bestaudio/best", "extract-audio": True}},
        "thumbnails": {"ydl_options": {"write-thumbnail": True}},
        "podcast": {"use": ["mp3", "thumbnails"], "ydl_options": {"add-metadata": True}},
    }
    result = expand_alias("podcast", aliases, [])
    assert result == {
        "format": "bestaudio/best",
        "extract-audio": True,
        "write-thumbnail": True,
        "add-metadata": True,
    }


def test_expand_alias_own_options_override_used_aliases():
    aliases = {
        "mp3": {"ydl_options": {"format": "bestaudio/best"}},
        "override": {"use": "mp3", "ydl_options": {"format": "custom/format"}},
    }
    assert expand_alias("override", aliases, [])["format"] == "custom/format"


def test_expand_uses_none_returns_empty_dict():
    assert expand_uses(None, {}, []) == {}


def test_expand_uses_merges_multiple_aliases():
    aliases = {
        "a": {"ydl_options": {"x": 1}},
        "b": {"ydl_options": {"y": 2}},
    }
    assert expand_uses(["a", "b"], aliases, []) == {"x": 1, "y": 2}


def test_resolve_aliases_mutates_config_in_place():
    config = {
        "aliases": {
            "mp3": {"ydl_options": {"format": "bestaudio/best"}},
            "podcast": {"use": "mp3", "ydl_options": {"add-metadata": True}},
        },
        "profiles": {
            "myprofile": {"use": ["podcast"], "ydl_options": {"output": "/x/%(title)s"}},
        },
    }
    resolve_aliases(config)

    assert config["aliases"]["podcast"]["ydl_options"] == {
        "format": "bestaudio/best",
        "add-metadata": True,
    }
    assert "use" not in config["aliases"]["podcast"]

    assert config["profiles"]["myprofile"]["ydl_options"] == {
        "format": "bestaudio/best",
        "add-metadata": True,
        "output": "/x/%(title)s",
    }
    assert "use" not in config["profiles"]["myprofile"]


def test_resolve_aliases_with_no_aliases_or_profiles_is_a_noop():
    config = {}
    resolve_aliases(config)  # should not raise
    assert config == {}


def test_resolve_aliases_profile_use_of_unknown_alias_raises():
    config = {
        "aliases": {},
        "profiles": {"p": {"use": "nope", "ydl_options": {}}},
    }
    with pytest.raises(Exception, match="Unknown alias"):
        resolve_aliases(config)
