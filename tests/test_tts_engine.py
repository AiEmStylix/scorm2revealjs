"""Tests cho tts_engine — split text, concat WAV, dispatch + map_ordered_tasks.

Không gọi mạng: chỉ test pure helpers (split/concat/order) và nhánh google thiếu package.
"""

import io

import numpy as np
import pytest
import soundfile as sf

import app.core.tts_engine as te
from app.core.config import settings


def test_split_by_sentences():
    text = "Câu một. Câu hai! Câu ba? Câu cuối."
    parts = te._split_by_sentences(text, limit=100)
    assert len(parts) >= 3
    assert "".join(parts).replace(" ", "") == text.replace(" ", "")


def test_split_by_words_over_limit():
    text = "Đây là một câu rất dài " * 20
    parts = te._split_by_sentences(text, limit=100)
    assert len(parts) > 1
    # mọi đoạn phải ≤ ngưỡng (tính theo bytes)
    assert all(len(p.encode("utf-8")) <= 100 for p in parts)


def test_split_text_extra_long_single_sentence():
    text = "word " * 500
    parts = te._split_by_sentences(text, limit=50)
    assert len(parts) > 1
    assert all(len(p.encode("utf-8")) <= 50 for p in parts)


def test_synthesize_empty_raises():
    with pytest.raises(ValueError):
        te.synthesize("   ", "google", "vi-VN-Chirp3-HD-Zephyr")


def test_synthesize_invalid_provider_raises():
    with pytest.raises(ValueError):
        te.synthesize("hello", "nope", "v")


def test_synthesize_google_missing_package():
    """google-cloud-texttospeech chưa cài → raise RuntimeError có hướng dẫn, không crash."""
    try:
        import google.cloud.texttospeech  # noqa: F401

        pytest.skip("google-cloud-texttospeech đã cài, bỏ qua nhánh thiếu package.")
    except ImportError:
        with pytest.raises(RuntimeError, match="google-cloud-texttospeech"):
            te._synthesize_google("xin chào", "vi-VN-Chirp3-HD-Zephyr")


def test_concat_wavs():
    sr = 24000
    a = (0.5 * np.sin(np.linspace(0, 5, 8000))).astype(np.float32)
    b = (0.4 * np.cos(np.linspace(0, 5, 4000))).astype(np.float32)

    def wav_to_bytes(arr):
        buf = io.BytesIO()
        sf.write(buf, arr, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    def read_wav(b):
        return sf.read(io.BytesIO(b), dtype="float32")[0]

    merged = te._concat_wavs([wav_to_bytes(a), wav_to_bytes(b)])
    data, got_sr = sf.read(io.BytesIO(merged), dtype="float32")
    assert got_sr == sr
    assert len(data) == len(a) + len(b)
    # So sánh với việc đọc lại từng đoạn (cùng phép lượng tử PCM_16) rồi nối — nhất quán.
    expected = np.concatenate([read_wav(wav_to_bytes(a)), read_wav(wav_to_bytes(b))])
    assert np.allclose(data, expected, atol=1e-3)


def test_map_ordered_tasks_preserves_order():
    tasks = [f"t{i}" for i in range(10)]

    def fn(t):
        return f"x-{t}"

    out = te.map_ordered_tasks(tasks, fn, max_workers=3)
    assert out == [f"x-t{i}" for i in range(10)]


def test_map_ordered_tasks_single_no_threadpool():
    assert te.map_ordered_tasks(["a"], lambda x: x.upper()) == ["A"]


def test_synthesize_long_uses_concat(monkeypatch):
    """Text dài → gọi synthesize từng phần và nối. Mock _synthesize_long để tránh mạng."""
    calls = []

    def fake_synth(p, provider, voice, model, normalize=True):
        calls.append(p)
        buf = io.BytesIO()
        sf.write(buf, np.zeros(1000, dtype=np.float32), 24000, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    monkeypatch.setattr(te, "synthesize", fake_synth)
    out = te._synthesize_long("Đây là một đoạn văn việt. " * 400, "google", "v", None)
    assert isinstance(out, bytes)
    assert len(calls) > 1


def test_is_transient_connection():
    assert te._is_transient(RuntimeError("Connection error.")) is True
    assert te._is_transient(RuntimeError("APIConnectionError: <!DOCTYPE html> 502 Bad gateway")) is True
    assert te._is_transient(RuntimeError("rate limit 429")) is True
    assert te._is_transient(RuntimeError("Error code: 409 - duplicate request")) is True


def test_is_transient_not_config_error():
    assert te._is_transient(ValueError("Giọng không tồn tại trong catalog")) is False
    assert te._is_transient(RuntimeError("400 model not found")) is False


def test_synthesize_retries_transient_then_success(monkeypatch):
    calls = {"n": 0}

    def fake_once(stripped, provider, voice, model):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("Connection error.")
        return b"WAVDATA"

    monkeypatch.setattr(te, "_call_once", fake_once)
    monkeypatch.setattr(settings, "tts_retry_attempts", 4)
    monkeypatch.setattr(settings, "tts_retry_base_delay", 0.01)
    out = te.synthesize("xin chào", "beeknoee", "v", "m")
    assert calls["n"] == 3
    assert out == b"WAVDATA"


def test_synthesize_raises_after_retries(monkeypatch):
    def fake_once(stripped, provider, voice, model):
        raise RuntimeError("Connection error. hết hạn")

    monkeypatch.setattr(te, "_call_once", fake_once)
    monkeypatch.setattr(settings, "tts_retry_attempts", 2)
    monkeypatch.setattr(settings, "tts_retry_base_delay", 0.01)
    import pytest as _pytest

    with _pytest.raises(RuntimeError):
        te.synthesize("xin chào", "beeknoee", "v", "m")
