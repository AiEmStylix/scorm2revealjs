"""BƯỚC 1 — Transform: Markdown đánh số → Reveal.js HTML sections.

Gọi LLM để chuyển nội dung mỗi slide thành 1 <section> Reveal.js.
Prompt yêu cầu giữ nguyên nội dung, LaTeX, bảng, danh sách; thêm fragment animations.
"""

import logging
import re

from app.core.llm_client import call_llm_text

logger = logging.getLogger(__name__)

_TRANSFORM_SYSTEM_PROMPT = """\
Bạn là chuyên gia chuyển đổi nội dung bài giảng thành slide Reveal.js.

NHIỆM VỤ: Nhận nội dung text của các slide bài giảng (đánh số ---SLIDE_N---), chuyển mỗi slide \
thành ĐÚNG 1 thẻ <section> HTML cho Reveal.js.

QUY TẮC BẮT BUỘC:
1. Mỗi slide → đúng 1 <section>...</section>. Số lượng <section> PHẢI BẰNG số slide đầu vào.
2. Giữ NGUYÊN nội dung gốc, tiếng Việt có dấu. KHÔNG thêm, bớt, hoặc bịa nội dung.
3. Công thức toán/hoá: bọc trong \\( ... \\) (inline) hoặc \\[ ... \\] (block) — Reveal.js MathJax.
4. Bảng → HTML <table> với class "table" (có border, dễ đọc).
5. BẮT BUỘC có Animation (Fragment): Mọi danh sách `<li>` và các đoạn text/ảnh quan trọng ĐỀU PHẢI có `class="fragment fade-up"` (hoặc fade-in, zoom-in) để nội dung hiện ra từ từ.
6. Màu nền (Background): Để slide ấn tượng, hãy thêm thuộc tính `data-background-gradient` vào các `<section>` với các dải màu hiện đại, ví dụ: `linear-gradient(to bottom right, #2c3e50, #3498db)`, hoặc `linear-gradient(135deg, #667eea 0%, #764ba2 100%)`. Hãy sáng tạo các màu gradient khác nhau cho các slide.
7. Transition & Auto-animate: Thêm `data-transition="zoom"` (hoặc fade, convex) vào `<section>`. Nếu slide có nội dung kéo dài sang slide sau, dùng `data-auto-animate` trên cả 2 slide.
8. Tiêu đề slide → <h2> (tiêu đề chính) hoặc <h3> (tiêu đề phụ).
9. Đoạn văn → <p>.
10. Ảnh/biểu đồ không trích được → ghi <p class="text-muted"><em>[Hình ảnh/biểu đồ]</em></p>.
11. Slide trống (không có chữ) → <section><h2>&nbsp;</h2></section>.
12. KHÔNG thêm thẻ <html>, <head>, <body>, <div class="reveal">, hay bất kỳ wrapper nào. \
Chỉ trả các thẻ <section>...</section> liền nhau.

ĐỊNH DẠNG ĐẦU RA: Chỉ trả HTML thuần (các thẻ <section> liền nhau), KHÔNG markdown, \
KHÔNG giải thích, KHÔNG code fence.
"""


def _count_slides(markdown: str) -> int:
    """Đếm số slide trong markdown đánh số ---SLIDE_N---."""
    return len(re.findall(r"---SLIDE_\d+---", markdown))


def _count_sections(html: str) -> int:
    """Đếm số <section> trong HTML output."""
    return len(re.findall(r"<section[\s>]", html, re.IGNORECASE))


def transform_to_revealjs(markdown: str) -> str:
    """Chuyển markdown đánh số slide → HTML sections cho Reveal.js.

    Args:
        markdown: nội dung markdown với format ---SLIDE_N---.

    Returns:
        HTML string chứa các <section>...</section>.

    Raises:
        ValueError: nếu số <section> output không khớp số slide input (sau 2 lần thử).
    """
    expected = _count_slides(markdown)
    if expected == 0:
        raise ValueError("Markdown không chứa slide nào (không tìm thấy ---SLIDE_N---).")

    logger.info("[Transform] %d slide → Reveal.js sections...", expected)

    user_content = (
        f"Bài giảng có {expected} slide. Chuyển đổi thành ĐÚNG {expected} thẻ <section>.\n\n"
        f"{markdown}"
    )

    # Thử tối đa 2 lần
    for attempt in range(2):
        html = call_llm_text(_TRANSFORM_SYSTEM_PROMPT, user_content)

        # Loại bỏ code fence nếu LLM bọc trong ```html ... ```
        html = re.sub(r"^```(?:html)?\s*\n?", "", html)
        html = re.sub(r"\n?```\s*$", "", html)
        html = html.strip()

        actual = _count_sections(html)
        if actual == expected:
            logger.info("[Transform] OK — %d sections.", actual)
            return html

        logger.warning(
            "[Transform] Lần %d: expected %d sections, got %d. %s",
            attempt + 1, expected, actual,
            "Thử lại..." if attempt == 0 else "Dùng bản hiện tại.",
        )

    # Nếu lần 2 vẫn lệch → vẫn trả kết quả (tốt hơn là crash)
    logger.warning("[Transform] Số section lệch nhưng vẫn sử dụng kết quả.")
    return html
