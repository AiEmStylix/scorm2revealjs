"""Tests cho step2_revealjs — ghép HTML Reveal.js (không cần LLM/PDF)."""

from app.pipeline.step2_revealjs import build_revealjs_html


def test_build_revealjs_html_contains_parts(sample_sections_html):
    html = build_revealjs_html("Bài Giảng", sample_sections_html)

    assert "<!DOCTYPE html>" in html
    assert "lang=\"vi\"" in html
    assert "<title>Bài Giảng</title>" in html
    assert "reveal.js@6.0.1" in html
    assert "Reveal.initialize" in html
    assert "RevealMath.MathJax3" in html
    assert "RevealHighlight" in html
    # Sections được chèn nguyên vẹn
    assert '<section data-transition="zoom"><h2>T1</h2></section>' in html


def test_build_revealjs_html_respects_theme_transition(sample_sections_html):
    html = build_revealjs_html(
        "T", sample_sections_html, theme="night", transition="fade", transition_speed="fast"
    )
    assert 'dist/theme/night.css' in html
    assert "transition: 'fade'" in html
    assert "transitionSpeed: 'fast'" in html


def test_build_revealjs_html_double_braces(sample_sections_html):
    """Template f-string dùng {{ }} nên không có dấu ngoặc đơn lẻ trong CSS/JS."""
    html = build_revealjs_html("T", sample_sections_html)
    assert "{font-family:" not in html
    assert "{ " not in html


def test_build_revealjs_html_tts_injection(sample_sections_html):
    manifest = {
        "provider": "beeknoee",
        "voice": "vi-VN-Chirp3-HD-Zephyr",
        "slides": [
            {
                "index": 0,
                "fragments": True,
                "lines": [{"idx": 0, "text": "Dòng 1", "audio": "audio/abc.wav"}],
            }
        ],
    }
    html = build_revealjs_html(
        "T", sample_sections_html, tts_manifest=manifest, tts_audio_base="/jobs/x/"
    )
    assert "window.TTS_MANIFEST" in html
    assert "\"audio/abc.wav\"" in html
    assert "window.TTS_AUDIO_BASE='/jobs/x/'" in html
    assert "fragmentshown" in html
    # Không tts_manifest → không nhúng engine
    assert "TTS_MANIFEST" not in build_revealjs_html("T", sample_sections_html)
