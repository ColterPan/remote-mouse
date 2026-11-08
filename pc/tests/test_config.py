"""Tests for config.py — loading, repairing and saving settings."""

import json

from remote_mouse.config import (
    DEFAULT_PORT,
    Config,
    default_config_dir,
    is_valid_token,
    load_config,
    new_token,
    save_config,
    with_new_token,
)


def test_new_tokens_are_valid_and_unique():
    tokens = {new_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(is_valid_token(t) for t in tokens)


def test_missing_file_creates_fresh_config(tmp_path):
    path = tmp_path / "sub" / "config.json"
    config = load_config(path)
    assert is_valid_token(config.token)
    assert config.port == DEFAULT_PORT
    assert json.loads(path.read_text()) == {
        "token": config.token,
        "port": DEFAULT_PORT,
        "discovery": True,
    }


def test_discovery_can_be_turned_off(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"token": new_token(), "port": 8765, "discovery": False}))
    assert load_config(path).discovery is False


def test_invalid_discovery_value_defaults_to_on(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"token": new_token(), "port": 8765, "discovery": "nope"}))
    assert load_config(path).discovery is True


def test_token_is_stable_across_loads(tmp_path):
    path = tmp_path / "config.json"
    assert load_config(path).token == load_config(path).token


def test_valid_file_is_loaded_unchanged(tmp_path):
    path = tmp_path / "config.json"
    original = Config(token=new_token(), port=9000)
    save_config(original, path)
    assert load_config(path) == original


def test_corrupt_file_is_repaired(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ this is not json")
    config = load_config(path)
    assert is_valid_token(config.token)
    assert json.loads(path.read_text())["token"] == config.token


def test_non_object_json_is_repaired(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[1, 2]")
    assert is_valid_token(load_config(path).token)


def test_invalid_fields_are_replaced(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"token": "short", "port": True}))
    config = load_config(path)
    assert config.token != "short"
    assert config.port == DEFAULT_PORT


def test_out_of_range_port_falls_back_to_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"token": new_token(), "port": 80}))
    assert load_config(path).port == DEFAULT_PORT


def test_with_new_token_returns_new_object():
    original = Config(token=new_token(), port=9000)
    updated = with_new_token(original)
    assert updated is not original
    assert updated.token != original.token
    assert updated.port == 9000


def test_default_config_dir_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert default_config_dir() == tmp_path / "RemoteMouse"
