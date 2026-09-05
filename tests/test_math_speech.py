"""Tests cho math_speech — đọc đúng cấu trúc LaTeX (frac/sqrt/mũ/chỉ số/hàm)."""

import app.core.math_speech as ms
import app.core.tts_text as tt


def test_linear_inequality():
    assert ms.latex_math_to_vietnamese("-5 < -2 < 0 < 3") == "âm 5 nhỏ hơn âm 2 nhỏ hơn 0 nhỏ hơn 3"


def test_addition_with_negative():
    assert ms.latex_math_to_vietnamese("(-3) + (-5) = -8") == "âm 3 cộng âm 5 bằng âm 8"


def test_subtraction_formula():
    out = ms.latex_math_to_vietnamese("a - b = a + (-b)")
    assert out == "a trừ b bằng a cộng âm b"


def test_standalone_leftrightarrow():
    assert ms.latex_math_to_vietnamese(r"\Leftrightarrow") == "tương đương"


def test_fraction():
    assert ms.latex_math_to_vietnamese(r"\frac{1}{2}") == "1 phần 2"


def test_fraction_nested():
    assert "phần" in ms.latex_math_to_vietnamese(r"\frac{a+b}{c}")


def test_sqrt():
    assert ms.latex_math_to_vietnamese(r"\sqrt{x^2+1}") == "căn bậc hai của x bình phương cộng 1"


def test_sqrt_nth():
    assert ms.latex_math_to_vietnamese(r"\sqrt[3]{8}") == "căn bậc 3 của 8"


def test_superscript():
    assert ms.latex_math_to_vietnamese(r"x^{2} + y^{2} = z^{2}") == "x bình phương cộng y bình phương bằng z bình phương"


def test_superscript_square_cube_pow():
    assert ms.latex_math_to_vietnamese(r"x^2") == "x bình phương"
    assert ms.latex_math_to_vietnamese(r"x^3") == "x lập phương"
    assert ms.latex_math_to_vietnamese(r"x^n") == "x mũ n"


def test_chemical_and_greek():
    # Giữ nguyên token hoá (CH4/H2O/CO2) như §C2; mũi tên toá n "suy ra".
    assert "CH4" in ms.latex_math_to_vietnamese(r"CH4 + 2O2 -> CO2 + 2H2O")
    assert "suy ra" in ms.latex_math_to_vietnamese(r"CH4 + 2O2 -> CO2")
    # Chữ Hy Lạp đọc tên quốc tế, không phiên âm.
    assert ms.latex_math_to_vietnamese(r"\alpha + \beta = \Delta") == "alpha cộng beta bằng delta"


def test_percent_and_degree():
    assert "phần trăm" in ms.latex_math_to_vietnamese(r"50\%")
    assert "độ C" in ms.latex_math_to_vietnamese(r"25^\circ C")


def test_subscript_and_degree():
    assert "chỉ số" in ms.latex_math_to_vietnamese(r"a_{i}")
    assert ms.latex_math_to_vietnamese(r"\sin(30^\circ)") == "sin của 30 độ"


def test_text_inline():
    out = ms.latex_math_to_vietnamese(r"x \leq 5 \text{ và } x > 0")
    assert "và" in out
    assert "lớn hơn" in out


def test_mixed_prose_math_via_tts():
    out = tt.to_tts_text(r"Với a < b \(\Leftrightarrow\) a nằm bên trái b.")
    assert out == "Với a nhỏ hơn b tương đương a nằm bên trái b."


def test_bare_latex_in_prose():
    # math chưa được bọc delimiter vẫn đọc tốt
    assert tt.to_tts_text(r"\frac{1}{2} số học sinh") == "1 phần 2 số học sinh"
