"""Tests cho step1_transform — đếm slide/section + retry mỗi khi không cần LLM thật.

validate logic bằng cách mock call_llm_text.
"""

import pytest

import app.pipeline.step1_transform as st


def test_count_slides():
    md = "---SLIDE_1---\nx\n---SLIDE_2---\ny\n"
    assert st._count_slides(md) == 2


def test_count_slides_none():
    assert st._count_slides("không có slide") == 0


def test_count_sections():
    html = "<section>a</section>\n<section data-x> b</section>"
    assert st._count_sections(html) == 2


def test_transform_raises_when_no_slides():
    with pytest.raises(ValueError):
        st.transform_to_revealjs("nothing here")


def test_transform_strips_code_fence_and_matches(monkeypatch, sample_markdown):
    """LLM trả fenced html với đủ section → phải strip fence và return đúng."""
    raw = "```html\n<section>1</section>\n<section>2</section>\n<section>3</section>\n```"

    def fake_call(system, user):
        return raw

    monkeypatch.setattr(st, "call_llm_text", fake_call)
    out = st.transform_to_revealjs(sample_markdown)

    assert out.startswith("<section>")
    assert not out.startswith("```")
    assert "```" not in out
    assert st._count_sections(out) == 3


def test_transform_retries_then_uses_last(monkeypatch, sample_markdown):
    """Lần 1 sai số section, lần 2 đúng → trả kết quả lần 2."""
    calls = {"n": 0}

    def fake_call(system, user):
        calls["n"] += 1
        if calls["n"] == 1:
            return "<section>chỉ 1</section>"
        return "<section>1</section>\n<section>2</section>\n<section>3</section>"

    monkeypatch.setattr(st, "call_llm_text", fake_call)
    out = st.transform_to_revealjs(sample_markdown)

    assert calls["n"] == 2
    assert st._count_sections(out) == 3
