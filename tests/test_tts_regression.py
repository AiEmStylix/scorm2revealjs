"""Regression tests — catch các lỗi tiếng nói từng mắc phải với slide lập trình + công thức.

Các case "đã từng sai" (xem báo cáo phân tích) không được phép tái xuất hiện:
- prose chứa \\ % & | < > * / ++ == != ... bị đẩy nhầm sang parser LaTeX;
- scientific notation bị bể; comment C không bị lọc; toán tử đọc dính liền không có khoảng trắng.
"""

import app.core.math_speech as ms
import app.core.tts_text as tt


def test_bare_latex_frac_detected_as_math():
    assert tt.to_tts_text(r"\frac{1}{2} số học sinh") == "1 phần 2 số học sinh"


def test_bare_latex_sqrt_detected_as_math():
    assert tt.to_tts_text(r"\sqrt{x^2+1} là gì") == "căn bậc hai của x bình phương cộng 1 là gì"


def test_prose_with_backslash_not_math():
    # `#include <stdio.h>` / `%5.2f` chứa backslash/percent nhưng KHÔNG được bắt là math.
    out = tt.to_tts_text("Việc khai báo: #include <tên thư viện>")
    assert "include" in out
    assert out.count("thư viện") == 1


def test_scientific_notation_readable():
    assert "nhân 10 mũ âm 38" in tt.to_tts_text("3.4e-38 .. 3.4e+38")


def test_c_comment_stripped():
    out = tt.to_tts_text("a = (5>10) /* a == 0 */")
    assert "/*" not in out and "*/" not in out
    assert "bằngbằng" not in out


def test_operators_spaced_not_glued():
    out = tt.to_tts_text("a = 5>10")
    assert "bằng" in out
    assert "5lớn hơn10" not in out  # trước đây đọc dính liền


def test_equality_and_inequality():
    assert "bằngbằng" not in tt.to_tts_text("a == 0")
    assert "khác" in tt.to_tts_text("a != 0")


def test_increment_decrement():
    out = tt.to_tts_text("a++ hoặc ++a")
    assert "acộngcộng" not in out
    assert "cộng cộng" in out


def test_bitwise_shifts():
    assert ms.latex_math_to_vietnamese("a << n = a * 2^n") == "a dịch trái n bằng a nhân 2 mũ n"
    assert ms.latex_math_to_vietnamese("a >> n = a / 2^n") == "a dịch phải n bằng a chia 2 mũ n"


def test_bitwise_and_or():
    assert ms.latex_math_to_vietnamese(r"1 \& 1 = 1") == "1 và 1 bằng 1"
    assert "và" in ms.latex_math_to_vietnamese("a & b | c")
    assert "hoặc" in ms.latex_math_to_vietnamese("a & b | c")


def test_logic_symbols():
    assert ms.latex_math_to_vietnamese(r"\land \lor \lnot") == "và hoặc không"


def test_range_reads_to():
    assert tt.to_tts_text("-128 .. 127") == "âm 128 đến 127"
    assert "đến" in tt.to_tts_text("26 chữ cái A .. Z")


def test_ellipsis_not_range():
    assert "chấm chấm chấm" in tt.to_tts_text("Số nguyên dương: 1, 2, 3, ...")


def test_is_code_literal():
    assert tt.to_tts_text("int a=5; a++ /* x */", is_code=True) == "int a=5; a++ /* x */"
