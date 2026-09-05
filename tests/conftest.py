"""Shared fixtures + environment setup for tests.

Đảm bảo settings dùng file .env (không bắt buộc tồn tại) và không gọi LLM thật.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def sample_markdown() -> str:
    """Markdown đánh số ---SLIDE_N--- mẫu (dùng chung cho transform/step tests)."""
    return (
        "---SLIDE_1---\n"
        "Tiêu đề bài giảng\n"
        "Giới thiệu nội dung chính.\n"
        "---SLIDE_2---\n"
        "Nội dung slide hai: công thức \\(E = mc^2\\).\n"
        "---SLIDE_3---\n"
        "- Điểm một\n"
        "- Điểm hai\n"
    )


@pytest.fixture
def sample_sections_html() -> str:
    """HTML sections Reveal.js mẫu (output của step1)."""
    return (
        '<section data-transition="zoom"><h2>T1</h2></section>\n'
        '<section data-transition="fade"><h2>T2</h2></section>\n'
        '<section><h2>T3</h2></section>'
    )
