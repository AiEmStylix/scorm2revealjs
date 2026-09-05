"""LaTeX math → lời tiếng Việt khi đọc (recursive descent parser).

Đúng nguyên tắc của Slide Pro (prompts.py §C2): "TTS không biết LaTeX". Ở đây, trước khi text
tới TTS, ta đổi mọi ký hiệu toán thành CHỮ tiếng Việt, chỉ GIỮ NGUYÊN token chữ-số mà TTS
đọc đáng tin cậy (x, f(x), H2O, sin, cos, ln...). TTS chỉ còn nhận văn bản thuần.

Bảng quy ước đọc (bám sát §C2):
- + cộng ; − trừ ; × nhân ; ÷ chia ; = bằng ; ≠ khác ; ≈ xấp xỉ ; ≤/≥ ...
- x² "x bình phương" ; x³ "x lập phương" ; x^n "x mũ n" ; √a "căn bậc hai của a" ; a/b "a chia b"
- mũi tên ->/→/⇒ "suy ra" (toán) ; ⇌/↔ "thuận nghịch" ; ↑ "bay lên" ; ↓ "kết tủa"
- % "phần trăm" ; °C "độ C" ; π "pi", α "alpha", β "beta", Δ "delta" (tên quốc tế)
"""

import re

_NAME = re.compile(r"[A-Za-z]+")

# Chữ Hy Lạp + hằng số: đọc TÊN QUỐC TẾ (không phiên âm) — như §C2.
_SYMBOL = {
    "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta",
    "epsilon": "epsilon", "theta": "theta", "lambda": "lambda", "mu": "mu",
    "pi": "pi", "rho": "rho", "sigma": "sigma", "tau": "tau",
    "omega": "omega", "infty": "vô cùng", "circ": "độ", "degree": "độ",
    # Chữ Hy Lạp viết hoa thường gặp (tên quốc tế, không phiên âm).
    "Delta": "delta", "Alpha": "alpha", "Beta": "beta", "Gamma": "gamma",
    "Omega": "omega", "Pi": "pi", "Sigma": "sigma", "Theta": "theta",
    "Phi": "phi", "phi": "phi", "Lambda": "lambda", "Mu": "mu",
}

_FUNCTION = {
    "sin": "sin", "cos": "cô sin", "tan": "tang", "cot": "cô tang",
    "log": "log", "ln": "lô ga rít", "exp": "e mũ", "arcsin": "ac sin",
    "arccos": "ac cô sin", "arctan": "ac tang", "lim": "lim",
}

_TEXT_CMDS = {"text", "mathrm", "textrm", "operatorname", "mbox", "textbf", "textsf"}

_BINARY = {
    "times": "nhân", "cdot": "nhân", "ast": "nhân", "div": "chia",
    "pm": "cộng trừ", "mp": "trừ cộng",
    # Bitwise/logic thường gặp trong slide tin học (C, Python, ...).
    "land": "và", "wedge": "và", "lnot": "không", "neg": "không",
    "lor": "hoặc", "vee": "hoặc",
}
_RELATION = {
    "le": "nhỏ hơn hoặc bằng", "leq": "nhỏ hơn hoặc bằng", "leqslant": "nhỏ hơn hoặc bằng",
    "ge": "lớn hơn hoặc bằng", "geq": "lớn hơn hoặc bằng", "geqslant": "lớn hơn hoặc bằng",
    "ne": "khác", "neq": "khác", "approx": "xấp xỉ",
    "Leftrightarrow": "tương đương", "iff": "tương đương",
    "Rightarrow": "suy ra", "implies": "suy ra", "to": "tới", "rightarrow": "suy ra",
    "in": "thuộc", "notin": "không thuộc", "subset": "là tập con của", "supset": "chứa",
    "cup": "hợp", "cap": "giao",
    "forall": "với mọi", "exists": "tồn tại", "nexists": "không tồn tại",
    "sim": "đồng dạng", "cong": "bằng nhau",
    "approxeq": "xấp xỉ", "cdot": "nhân", "longrightarrow": "suy ra",
    # Gán/quan hệ trong slide lập trình.
    "equiv": "tương đương", "mid": "chia hết cho",
}
_OPERATORS = {
    "ll": "dịch trái", "gg": "dịch phải", "cdot": "nhân", "ast": "nhân",
    "star": "nhân", "oplus": "hoặc loại trừ", "otimes": "nhân mô đun",
    "arg": "đối số của", "operatorname": "toán tử",
}

# Hợp mọi lệnh latex MÀ TTS CẦN BIẾT. tts_text import để phân biệt "chắc chắn là math"
# (vd \sqrt, \frac) với chuỗi chứa backslash nhưng KHÔNG phải math (vd "#include <stdio.h>",
# "%5.2f", "\\t", "\\n", "\\&kết xuất" trong mã nguồn). Xem to_tts_text().
_STRUCTURAL = {
    "frac", "dfrac", "tfrac", "cfrac", "sqrt", "sum", "int", "prod",
    "left", "right", "begin", "end", "displaystyle", "cases", "matrix",
    "pmatrix", "bmatrix", "choose", "binom", "stackrel", "overset", "underset",
}
KNOWN_COMMANDS = frozenset().union(
    _SYMBOL, _FUNCTION, _TEXT_CMDS, _BINARY, _RELATION, _OPERATORS, _STRUCTURAL
)

_REL_CHARS = set("<>=~!")
_ARROWS = {
    "->": "suy ra", "=>": "suy ra",
    "\u2192": "suy ra", "\u21d2": "suy ra",  # → ⇒
    "\u21cc": "thuận nghịch", "\u2194": "thuận nghịch",  # ⇌ ↔
    "\u2191": "bay lên", "\u2193": "kết tủa",  # ↑ ↓
}
_MULTI_REL = {
    "<=": "nhỏ hơn hoặc bằng", ">=": "lớn hơn hoặc bằng", "!=": "khác",
    "==": "bằng",
}


class _Tokens:
    """Tokenize chuỗi LaTeX thành list token (tên, giá trị)."""

    def __init__(self, s: str):
        self.toks: list[tuple[str, str]] = []
        self._scan(s)

    def _scan(self, s: str) -> None:
        i, n = 0, len(s)
        while i < n:
            c = s[i]
            if c.isspace():
                i += 1
                continue
            if c == "\\":
                m = _NAME.match(s, i + 1)
                if m:
                    self.toks.append(("cmd", m.group()))
                    i = m.end()
                else:
                    i += 1
                continue
            two = s[i:i + 2]
            if two in _MULTI_REL:
                self.toks.append(("rel", _MULTI_REL[two]))
                i += 2
                continue
            if two in ("<<", ">>"):
                self.toks.append(("shift", two))
                i += 2
                continue
            if two in _ARROWS:
                self.toks.append(("arrow", _ARROWS[two]))
                i += 2
                continue
            if c in _ARROWS:
                self.toks.append(("arrow", _ARROWS[c]))
                i += 1
                continue
            if c in "{}":
                self.toks.append(("brace", c))
                i += 1
                continue
            if c in "^_":
                self.toks.append(("script", c))
                i += 1
                continue
            if c in "()[]":
                self.toks.append(("paren", c))
                i += 1
                continue
            if c in "+-*/=<>~!,;:%&|":
                self.toks.append(("op", c))
                i += 1
                continue
            if c in "\u00b0\u2212":  # ° − (dấu trừ toán học)
                self.toks.append(("op", "deg" if c == "\u00b0" else "-"))
                i += 1
                continue
            if s.startswith("...", i):
                self.toks.append(("op", "ellipsis"))
                i += 3
                continue
            if c == "\u2026":
                self.toks.append(("op", "ellipsis"))
                i += 1
                continue
            if c.isdigit():
                m = re.match(r"\d+(\.\d+)?", s[i:])
                if m:
                    self.toks.append(("num", m.group()))
                    i += len(m.group())
                else:
                    i += 1
                continue
            # Gộp cả cụm CHỮ (kể cả tiếng Việt) + chữ-số liền (H2O, CO2, CH4) thành 1 token.
            # Bắt đầu bằng chữ, theo sau chữ/số (KHÔNG gồm _ / ^ để không nuốt script).
            m = re.match(r"[^\W\d_][^\W_]*", s[i:])
            if m:
                self.toks.append(("word", m.group()))
                i += len(m.group())
                continue
            i += 1


class _Parser:
    def __init__(self, toks: list[tuple[str, str]]):
        self.t = toks
        self.i = 0

    def _peek(self) -> tuple[str, str] | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def _next(self) -> tuple[str, str] | None:
        tok = self._peek()
        if tok:
            self.i += 1
        return tok

    def _expect(self, kind: str, val: str | None = None) -> tuple[str, str] | None:
        tok = self._peek()
        if tok and tok[0] == kind and (val is None or tok[1] == val):
            return self._next()
        return None

    def _expr(self) -> str:
        out = self._add()
        while True:
            tok = self._peek()
            if tok is None:
                break
            if tok[0] == "cmd" and tok[1] in _TEXT_CMDS:
                self._next()
                out = f"{out} {self._group()}"
                continue
            rel = self._relation_word(tok)
            if rel is None:
                break
            self._next()
            out = f"{out} {rel} {self._add()}"
        return out

    def _relation_word(self, tok) -> str | None:
        if not tok:
            return None
        if tok[0] == "cmd":
            return _RELATION.get(tok[1])
        if tok[0] == "rel":
            return tok[1]
        if tok[0] == "arrow":
            return tok[1]
        if tok[0] == "op" and tok[1] in _REL_CHARS:
            return {"=": "bằng", "<": "nhỏ hơn", ">": "lớn hơn", "!": "khác", "~": "xấp xỉ"}[tok[1]]
        return None

    def _add(self) -> str:
        out = self._mul()
        while True:
            tok = self._peek()
            if tok and tok[0] == "cmd" and tok[1] in ("pm", "mp"):
                self._next()
                out = f"{out} {_BINARY[tok[1]]} {self._mul()}"
            elif tok and tok[0] == "op" and tok[1] in "+-":
                self._next()
                out = f"{out} {'cộng' if tok[1] == '+' else 'trừ'} {self._mul()}"
            elif tok and tok[0] == "shift":
                self._next()
                out = f"{out} {'dịch trái' if tok[1] == '<<' else 'dịch phải'} {self._mul()}"
            elif tok and tok[0] == "op" and tok[1] in "&|":
                self._next()
                out = f"{out} {'và' if tok[1] == '&' else 'hoặc'} {self._mul()}"
            elif tok and tok[0] == "arrow":
                self._next()
                out = f"{out} {tok[1]} {self._mul()}"
            else:
                break
        return out

    def _mul(self) -> str:
        out = self._unary()
        while True:
            tok = self._peek()
            if tok and tok[0] == "cmd" and tok[1] in _BINARY:
                self._next()
                out = f"{out} {_BINARY[tok[1]]} {self._unary()}"
            elif tok and tok[0] == "op" and tok[1] in "*/":
                self._next()
                out = f"{out} {'nhân' if tok[1] == '*' else 'chia'} {self._unary()}"
            else:
                break
        return out

    def _unary(self) -> str:
        tok = self._peek()
        if tok and tok[0] == "op" and tok[1] in "-":
            self._next()
            return f"âm {self._unary()}"
        if tok and tok[0] == "op" and tok[1] in "+":
            self._next()
            return self._unary()
        return self._power()

    def _power(self) -> str:
        base = self._atom()
        while True:
            tok = self._peek()
            if tok and tok[0] == "script":
                self._next()
                nxt = self._peek()
                if tok[1] == "^" and nxt and nxt[0] == "cmd" and nxt[1] in ("circ", "degree"):
                    self._next()
                    base = f"{base} độ"
                    continue
                script = self._script_arg()
                if tok[1] == "^":
                    if script == "2":
                        base = f"{base} bình phương"
                    elif script == "3":
                        base = f"{base} lập phương"
                    else:
                        base = f"{base} mũ {script}"
                else:
                    base = f"{base} chỉ số {script}"
            elif tok and tok[0] == "op" and tok[1] == "%":
                self._next()
                base = f"{base} phần trăm"
            elif tok and tok[0] == "op" and tok[1] == "deg":
                self._next()
                base = f"{base} độ"
            else:
                break
        return base

    def _script_arg(self) -> str:
        if self._peek() and self._peek()[0] == "brace" and self._peek()[1] == "{":
            self._next()
            out = self._expr()
            self._expect("brace", "}")
            return out
        return self._atom()

    def _atom(self) -> str:
        tok = self._peek()
        if not tok:
            return ""
        kind, val = tok
        if kind == "num":
            self._next()
            return val
        if kind == "word":
            self._next()
            return val
        if kind == "op" and val in ",;:":
            self._next()
            return ""
        if kind == "op" and val == "ellipsis":
            self._next()
            return " chấm chấm chấm "
        if kind == "op" and val == "deg":
            self._next()
            return " độ "
        if kind == "brace" and val == "{":
            self._next()
            out = self._expr()
            self._expect("brace", "}")
            return out
        if kind == "paren":
            if val in "([":
                self._next()
                out = self._expr()
                if self._expect("cmd", "right") is None:
                    self._expect("paren", ")" if val == "(" else "]")
                return out
            self._next()
            return ""
        if kind == "cmd":
            if val in _RELATION or val in _BINARY:
                return ""  # toán tử — để vòng _expr/_add/_mul xử lý, KHÔNG nuốt làm toán hạng
            self._next()
            return self._command(val)
        return ""

    def _command(self, name: str) -> str:
        if name in _SYMBOL:
            return _SYMBOL[name]
        if name in _FUNCTION:
            return f"{_FUNCTION[name]} của {self._unary()}"
        if name in _OPERATORS:
            return _OPERATORS[name]
        if name in ("frac", "dfrac", "tfrac", "cfrac"):
            num = self._group()
            den = self._group()
            return f"{num} phần {den}" if den else num
        if name == "sqrt":
            n = None
            if self._expect("paren", "["):
                n = self._expr()
                self._expect("paren", "]")
            body = self._group()
            if n:
                return f"căn bậc {n} của {body}"
            return f"căn bậc hai của {body}"
        if name in _TEXT_CMDS:
            return self._group()
        if name in ("sum", "int", "prod"):
            return {"sum": "tổng", "int": "tích phân", "prod": "tích"}[name]
        if name in ("left", "right", "begin", "end", "cdot"):
            return ""
        return ""

    def _group(self) -> str:
        if self._expect("brace", "{"):
            out = self._expr()
            self._expect("brace", "}")
            return out
        return self._atom()

    def _render_rest(self) -> str:
        out = ""
        for kind, val in self.t[self.i:]:
            if kind in ("word", "num"):
                out += " " + val
            elif kind == "cmd":
                out += " " + (_SYMBOL.get(val) or _RELATION.get(val) or _FUNCTION.get(val) or _OPERATORS.get(val) or _BINARY.get(val) or "") + " "
            elif kind == "op":
                word = {"<": "nhỏ hơn", ">": "lớn hơn", "=": "bằng", "!": "khác", "~": "xấp xỉ",
                        "+": "cộng", "-": "trừ", "*": "nhân", "/": "chia", "%": "phần trăm",
                        "&": "và", "|": "hoặc"}.get(val, val)
                out += " " + word + " "
            elif kind == "shift":
                out += " " + ("dịch trái" if val == "<<" else "dịch phải") + " "
            elif kind in ("rel", "arrow"):
                out += " " + val + " "
            elif kind == "script":
                out += " mũ " if val == "^" else " chỉ số "
            else:
                out += " "
        return out


def latex_math_to_vietnamese(latex: str) -> str:
    """Chuỗi LaTeX (đã bỏ delimiter) → lời tiếng Việt mạch lạc khi đọc."""
    tokens = _Tokens(latex)
    parser = _Parser(tokens.toks)
    try:
        out = parser._expr()
        if parser.i < len(tokens.toks):
            out = f"{out} {parser._render_rest()}"
    except Exception:  # noqa: BLE001 - không để 1 công thức phá vỡ cả slide
        out = _fallback(latex)
    out = re.sub(r"\s+", " ", (out or "")).strip()
    return out or _fallback(latex)


def _fallback(latex: str) -> str:
    text = latex
    text = re.sub(r"\\([A-Za-z]+)", lambda m: " " + _SYMBOL.get(m.group(1), "") + " ", text)
    text = text.replace("->", " suy ra ").replace("=>", " suy ra ")
    text = re.sub(r"[\\{}^_&]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
