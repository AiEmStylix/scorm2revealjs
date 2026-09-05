"""Bình thường hoá text trước khi TTS — đọc như người thật, tiếng Việt, đọc đúng công thức.

Vấn đề: text lấy từ HTML/LaTeX còn nguyên công thức math (`\\(-5 < -2 < 0 < 3\\)`,
`\\frac{a+b}{c}`, `x^{2}`, `\\Leftrightarrow`). Đưa thẳng vào Gemini TTS khiến model:
- tự đoán ngôn ngữ → dễ chuyển sang tiếng Anh,
- đọc ký hiệu LaTeX thành "backslash ..." rất khó hiểu.

Giải pháp:
- Segment được bọc delimiter `\\(...\\)`, `\\[...\\]`, `$...$` → gửi qua parser LaTeX
  (app/core/math_speech.py).
- Segment TRẦN (không delimiter) nhưng CHẮC CHẮN là math → gửi qua parser. Tiêu chí "chắc
  chắn" = chứa một lệnh LaTeX ĐÃ BIẾT (\\sqrt, \\frac, \\times ...) — KHÔNG dùng backslash
  rời như trước, vì chuỗi lập trình `#include <stdio.h>`, `%5.2f`, `\\t`, `\\n` chứa
  backslash nhưng KHÔNG phải math.
- Còn lại (prose thuần) → dọn ký hiệu đơn giản bằng "prose normalizer" riêng.
- `is_code=True`: trả text nguyên bản (chỉ gỡ fence) — mã nguồn đọc literal.

Sau đó nối lại các segment, dọn khoảng trắng trước dấu câu.
"""

import re

from app.core.math_speech import KNOWN_COMMANDS, latex_math_to_vietnamese

# Delimiters của math wrapping (không đọc chúng, chỉ dùng để tách segment).
_OPEN1, _CLOSE1 = re.escape(r"\("), re.escape(r"\)")
_OPEN2, _CLOSE2 = re.escape(r"\["), re.escape(r"\]")
_MATH_SPLIT_RE = re.compile(
    f"({_OPEN1}.*?{_CLOSE1}|{_OPEN2}.*?{_CLOSE2}|\\$\\$.*?\\$\\$|\\$.*?\\$)",
    re.DOTALL,
)

# Delimiters → khoảng trắng (bỏ khi lấy nội dung math).
_DELIM_RE = re.compile(f"{_OPEN1}|{_CLOSE1}|{_OPEN2}|{_CLOSE2}|\\$\\$|\\$")

# Lệnh LaTeX ĐÃ BIẾT, kèm cú pháp trước nó \x → dùng để nhận biết segment "chắc chắn math".
_CMD_HINT_RE = re.compile(
    r"\\(" + "|".join(sorted(KNOWN_COMMANDS, key=len, reverse=True)) + r")\b"
)

# Ký tự/chuỗi GIỐNG math nhưng thực ra là mã nguồn / định dạng → không được bắt là math.
# (vd "\t", "\n", "\*p", "a \& b" trong C). Nếu segment toàn là mấy thứ này → prose.
_CODEISH_MARKERS = re.compile(
    r"#include|#define|printf\(|scanf\(|getch\(|getchar\(|%[-+0-9 .]*[diufsclxeE%]|\\[tnrb0\)]"
)


def _strip_math_delim(seg: str) -> str:
    return _DELIM_RE.sub(" ", seg).strip()


def _contains_known_cmd(seg: str) -> bool:
    """Segment trần có chứa lệnh LaTeX đã biết (\\sqrt, \\frac, \\times ...).

    Loại trừ các backslash giống mã nguồn / định dạng (\\t, \\n, %5.2f, #include ...).
    """
    seg = _strip_math_delim(seg)
    if _CODEISH_MARKERS.search(seg):
        return False
    return bool(_CMD_HINT_RE.search(seg))


# ---------------------------------------------------------------------------
# Prose normalizer: dọn văn xuôi KHÔNG phải math — tiếng Việt đọc được.
# Xử lý: comment C, scientific notation, toán tử cơ bản (có khoảng trắng), dải giá trị.
# ---------------------------------------------------------------------------

# Comment C: /* ... */ và // ... (đến cuối đoạn) → bỏ.
_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)

# Scientific notation: "3.4e-38" → "3.4 nhân 10 mũ âm 38" (đọc rõ ràng, không đọc "e trừ").
_SCINOT_RE = re.compile(
    r"(?<![A-Za-z])(\d+(?:\.\d+)?)[eE]([+-]?\d+)(?!\d)"
)

# Dải giá trị "x .. y" / "x ... y" / "x…y" → "x đến y" (CHỈ giữa 2 token, không phải ellipsis
# lửng lơ ở đầu/cuối danh sách — trường hợp đó để "chấm chấm chấm").
_RANGE_RE = re.compile(r"(?<=\w)\s*(?:\.\.\.|\.\.|…)\s*(?=\w)", re.UNICODE)


def _scinot_sub(m: "re.Match") -> str:
    num, exp = m.group(1), m.group(2)
    sign = exp[0] if exp[0] in "+-" else ""
    digits = exp[1:] if sign else exp
    return f"{num} nhân 10 mũ {('âm ' if sign == '-' else '')}{digits}"


def _prose_segment(seg: str) -> str:
    """Dọn segment KHÔNG phải math (văn xuôi / mã giả) thành text đọc được."""
    text = _COMMENT_RE.sub(" ", seg)

    # Scientific notation trước (giữ nguyên cấu trúc số).
    text = _SCINOT_RE.sub(_scinot_sub, text)

    # Số âm: dấu "-" đứng ngay trước chữ số (không đứng sau chữ/số/>)") → "âm".
    text = re.sub(r"(?<![A-Za-z0-9)])\s*-(?=\d)", " âm ", text)

    # Dải giá trị: "A .. B" / "A...B" → "A đến B".
    text = _RANGE_RE.sub(" đến ", text)

    # Ellipsis dư → "chấm chấm chấm".
    text = re.sub(r"\.\.\.|…", " chấm chấm chấm ", text)

    # Bỏ backslash + ngoặc nhọn rời.
    text = re.sub(r"[\\{}]", " ", text)

    # Gộp dấu "==" / "!=" / "++" / "--" / "<=" / ">=" TRƯỚC khi đổi ký tự đơn.
    text = re.sub(r"\s*==\s*", " bằng ", text)
    text = re.sub(r"\s*!=\s*", " khác ", text)
    text = re.sub(r"\+\+", " cộng cộng ", text)
    text = re.sub(r"--", " trừ trừ ", text)  # PHẢI sau số âm (đã đổi "-"→"âm" trước)
    text = re.sub(r"--", " trừ trừ ", text)
    text = re.sub(r"\s*<=\s*", " nhỏ hơn hoặc bằng ", text)
    text = re.sub(r"\s*>=\s*", " lớn hơn hoặc bằng ", text)
    text = re.sub(r"&&", " và ", text)
    text = re.sub(r"\|\|", " hoặc ", text)

    # Bỏ dấu ngoặc đơn không cần thiết trong prose.
    text = re.sub(r"[()]", " ", text)

    # Toán tử đơn → từ tiếng Việt (có khoảng trắng quanh từ).
    text = text.replace("*", " nhân ")
    text = text.replace("/", " chia ")
    text = text.replace("%", " phần trăm ")
    text = text.replace("<", " nhỏ hơn ")
    text = text.replace(">", " lớn hơn ")
    text = text.replace("=", " bằng ")  # dấu "=" rời (đã gộp == trước)
    text = text.replace("+", " cộng ")
    text = text.replace("-", " ")  # dấu trừ còn lại trong prose = gạch nối → ngắt nghỉ
    text = text.replace("&", " và ")
    text = text.replace("|", " hoặc ")
    text = text.replace("~", " xấp xỉ ")
    text = text.replace("!", " khác ")  # riêng lẻ (đã gộp != trước)

    return text


def to_tts_text(raw: str, *, is_code: bool = False) -> str:
    """Bình thường hoá text (HTML/LaTeX) → văn bản tiếng Việt đọc được, đọc đúng công thức.

    Args:
        raw: text thô (có thể chứa HTML entity đã được decode, LaTeX, toán tử...).
        is_code: True nếu đây là MÃ NGUỒN — trả literal (chỉ gỡ fence/tex delimiter),
            span KHÔNG biến ký hiệu thành chữ.
    """
    if not raw:
        return ""
    if is_code:
        text = re.sub(r"```[a-zA-Z]*", " ", raw)
        text = re.sub(_MATH_SPLIT_RE, lambda m: _strip_math_delim(m.group(0)), text)
        text = re.sub(r"[\\{}]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    if _MATH_SPLIT_RE.search(raw):
        parts = _MATH_SPLIT_RE.split(raw)
    else:
        parts = [raw]

    out: list[str] = []
    for i, seg in enumerate(parts):
        seg = seg.strip()
        if not seg:
            continue
        if (i % 2 == 1) or _contains_known_cmd(seg):
            inner = _strip_math_delim(seg)
            out.append(latex_math_to_vietnamese(inner))
        else:
            out.append(_prose_segment(seg))

    text = " ".join(out)
    # Dọn khoảng trắng trước dấu câu + gộp.
    text = re.sub(r"\s+([.,;:!?…])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
