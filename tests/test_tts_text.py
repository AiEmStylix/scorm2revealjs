"""Tests cho tts_text — dọn LaTeX/toán → tiếng Việt đọc được, không còn ký hiệu gây đổi giọng."""

import app.core.tts_text as tt


def test_strips_latex_delimiters():
    out = tt.to_tts_text(r"Ví dụ: \(a - b\)")
    assert r"\(" not in out and r"\)" not in out


def test_maps_leftrightarrow():
    out = tt.to_tts_text(r"Với a < b \(\Leftrightarrow\) a nằm bên trái b.")
    assert "tương đương" in out
    assert "nhỏ hơn" in out
    assert r"\Leftrightarrow" not in out


def test_negative_numbers():
    out = tt.to_tts_text(r"\(-5 < -2 < 0 < 3\)")
    assert "âm 5" in out
    assert "âm 2" in out
    # không còn dấu "-" đứng trước số
    assert "-2" not in out


def test_subtraction_preserved():
    out = tt.to_tts_text(r"\(a - b = a + (-b)\)")
    assert "trừ" in out
    assert "bằng" in out


def test_clean_plain_vietnamese_passthrough():
    out = tt.to_tts_text("Số nguyên gồm các số âm và số dương.")
    assert out == "Số nguyên gồm các số âm và số dương."


def test_math_example_reads_clean():
    out = tt.to_tts_text(r"Ví dụ: \((-3) + (-5) = -8\)")
    assert "cộng" in out
    assert "bằng" in out
    assert "âm" in out
    assert "\\" not in out


def test_ellipsis_ok():
    assert "chấm chấm chấm" in tt.to_tts_text("Số nguyên dương: 1, 2, 3, ...")
