"""Tests cho step1_tts — parse fragment lines + synthesize_tts với TTS được mock."""

import io
import shutil
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

import app.core.tts_engine as engine
import app.pipeline.step1_tts as st
from app.core.usage import TTSUsage

SECTIONS = (
    '<section><h2>T1</h2>'
    '<ul>'
    '<li class="fragment fade-up">Dòng 1</li>'
    '<li class="fragment fade-up">Dòng 2</li>'
    '</ul>'
    '</section>\n'
    '<section><h2>T2</h2><p>Không có fragment</p></section>'
)


def _fake_wav():
    buf = io.BytesIO()
    sf.write(buf, np.zeros(2000, dtype=np.float32), 24000, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def test_extract_slide_lines_fragments():
    slides = st.extract_slide_lines(SECTIONS)
    assert len(slides) == 2
    assert slides[0]["fragments"] is True
    assert [l["text"] for l in slides[0]["lines"]] == ["Dòng 1", "Dòng 2"]
    assert slides[1]["fragments"] is False


def test_extract_code_read_literal():
    """Mã nguồn (thẻ <code>/<pre>) đọc LITERAL — không biến `#include <...>`/`++` thành chữ vô nghĩa."""
    from bs4 import BeautifulSoup

    html = '<pre class="fragment"><code>#include &lt;stdio.h&gt;\nint main(){ printf("%d", a=5); }</code></pre>'
    el = BeautifulSoup(html, "html.parser").find("pre")
    text = st._extract_text(el)
    assert "#include <stdio.h>" in text  # giữ nguyên ký hiệu, không thành "nhỏ hơn...lớn hơn"
    assert "nhỏ hơn" not in text
    assert "cộng cộng" not in text


def test_extract_math_read_cleaned():
    from bs4 import BeautifulSoup

    html = '<p class="fragment">Ví dụ: \\(-5 < -2 < 0 < 3\\)</p>'
    el = BeautifulSoup(html, "html.parser").find("p")
    text = st._extract_text(el)
    assert "nhỏ hơn" in text and "âm 5" in text and "\\" not in text


def test_synthesize_tts_manifest(monkeypatch):
    def fake_synth(text, provider, voice, model=None, normalize=True):
        return _fake_wav()

    monkeypatch.setattr(engine, "synthesize", fake_synth)
    audio_dir = Path(tempfile.mkdtemp())
    try:
        usage = TTSUsage()
        manifest = st.synthesize_tts(SECTIONS, audio_dir, voice_id="zephyr", usage=usage)
        assert all(l["text"] for l in manifest["slides"][0]["lines"])
        assert all(l["audio"] for l in manifest["slides"][0]["lines"])
        # slide 2 không fragment → 1 dòng, audio có đường dẫn
        assert manifest["slides"][1]["lines"][0]["audio"]
        assert usage.synthesized_chars > 0
        # idempotency: chạy lại cho cùng đường dẫn audio (reuse, không synth lại)
        usage2 = TTSUsage()
        manifest2 = st.synthesize_tts(SECTIONS, audio_dir, voice_id="zephyr", usage=usage2)
        assert (
            manifest2["slides"][0]["lines"][0]["audio"]
            == manifest["slides"][0]["lines"][0]["audio"]
        )
        # manifest trỏ audio/<hash>.wav; file phải nằm ĐÚNG ở audio_dir/<hash>.wav (không đúp subdir)
        ref = manifest["slides"][1]["lines"][0]["audio"]
        assert ref.startswith("audio/")
        assert (audio_dir / Path(ref).name).exists(), "file phải nằm ngay trong audio_dir"
        assert not (audio_dir / ref).exists(), "KHÔNG được nằm trong audio_dir/audio/ (đúp subdir)"
    finally:
        shutil.rmtree(audio_dir, ignore_errors=True)


def test_dedupe_identical_content_synthesized_once(monkeypatch):
    """Nội dung trùng (cùng voice+text) chỉ synth 1 lần, mọi dòng chung 1 audio — tránh 409 duplicate."""
    calls = []

    def fake_synth(text, provider, voice, model=None, normalize=True):
        calls.append(text)
        return _fake_wav()

    monkeypatch.setattr(engine, "synthesize", fake_synth)
    sections = (
        '<section><ul>'
        '<li class="fragment">Dòng trùng A</li>'
        '<li class="fragment">Dòng trùng A</li>'
        '<li class="fragment">Dòng trùng A</li>'
        '</ul></section>\n'
        '<section><ul>'
        '<li class="fragment">Dòng trùng A</li>'
        '<li class="fragment">Dòng B</li>'
        '</ul></section>'
    )
    audio_dir = Path(tempfile.mkdtemp())
    try:
        manifest = st.synthesize_tts(sections, audio_dir, voice_id="zephyr")
        assert calls.count("Dòng trùng A") == 1, "chỉ synth 1 lần cho nội dung trùng"
        assert len(calls) == 2
        # mọi dòng trùng trỏ về CÙNG audio
        shared = [ln["audio"] for s in manifest["slides"] for ln in s["lines"] if ln["text"] == "Dòng trùng A"]
        assert len(set(shared)) == 1
        assert len(shared) == 4
    finally:
        shutil.rmtree(audio_dir, ignore_errors=True)


def test_synthesize_tts_line_error_continues(monkeypatch):
    def fake_synth(text, provider, voice, model=None, normalize=True):
        if text == "Dòng 1":
            raise RuntimeError("provider down")
        return _fake_wav()

    monkeypatch.setattr(engine, "synthesize", fake_synth)
    audio_dir = Path(tempfile.mkdtemp())
    try:
        usage = TTSUsage()
        manifest = st.synthesize_tts(SECTIONS, audio_dir, voice_id="zephyr", usage=usage)
        first = manifest["slides"][0]["lines"][0]
        assert first["audio"] is None
        assert manifest["slides"][0]["lines"][1]["audio"] is not None
        assert usage.synthesized_chars > 0
        assert any(not l.ok for l in usage.lines)
    finally:
        shutil.rmtree(audio_dir, ignore_errors=True)
