"""Tests cho tts_config — resolve() theo nguyên tắc: lệch voice_id → raise, không đọc giọng khác."""

import pytest

import app.core.tts_config as tc


def test_active_provider_default():
    cfg = tc.get_config()
    assert cfg.active_provider() in ("google", "beeknoee")


def test_resolve_default_voice():
    provider, voice, model = tc.resolve(None)
    assert voice  # luôn có tên voice thật
    # beeknoee phải có model; google native model None
    if provider == "beeknoee":
        assert model
    else:
        assert model is None


def test_resolve_known_voice():
    _, voice, _ = tc.resolve("zephyr")
    assert voice.endswith("-Zephyr") or voice == "zephyr"


def test_resolve_missing_voice_raises():
    with pytest.raises(ValueError):
        tc.resolve("khong-ton-tai-giong")


def test_catalog_has_both_providers():
    cfg = tc.get_config()
    assert "beeknoee" in cfg.voices
    assert "google" in cfg.voices
