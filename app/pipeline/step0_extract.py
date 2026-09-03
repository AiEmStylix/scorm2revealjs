"""BƯỚC 0 — Extract: PDF → Markdown đánh số ---SLIDE_N---.

Rút gọn từ spro/app/pipeline/step0_extract.py:
- Vision-LLM OCR mỗi trang PDF (song song qua ThreadPoolExecutor).
- Bỏ: JobStorage, progress reporting, multi-provider fallback, cảnh báo A2, extract_meta.
"""

import base64
import io
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.core.config import settings
from app.core.llm_client import call_llm_vision

logger = logging.getLogger(__name__)

_OCR_VISION_PROMPT = (
    "Trích xuất TOÀN BỘ nội dung CHỮ trong ảnh trang slide này thành văn bản. Giữ nguyên tiếng Việt "
    "có dấu, công thức hoá học/toán (dùng LaTeX nếu là công thức), bảng, danh sách theo thứ tự đọc. "
    "KHÔNG thêm giải thích, KHÔNG bịa nội dung không có trong ảnh. Nếu trang không có chữ, trả chuỗi rỗng."
)


def _resize_for_ocr(pix) -> bytes:
    """Resize ảnh trang trước khi gửi vision OCR — giảm token đầu vào."""
    from PIL import Image

    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    img.thumbnail((settings.slide_image_max_w, settings.slide_image_max_h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _ocr_one_page(pdf_path: Path, page_index: int) -> dict:
    """OCR 1 trang PDF bằng vision-LLM → {text, tok_in, tok_out}."""
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    try:
        pix = doc[page_index].get_pixmap(dpi=settings.render_dpi)
    finally:
        doc.close()

    b64 = base64.b64encode(_resize_for_ocr(pix)).decode()

    try:
        text, tok_in, tok_out = call_llm_vision(_OCR_VISION_PROMPT, b64)
        return {"text": text, "in": tok_in, "out": tok_out, "page": page_index}
    except Exception as e:
        logger.warning("[OCR] Trang %d lỗi: %s → để trống.", page_index + 1, e)
        return {"text": "", "in": 0, "out": 0, "page": page_index}


def extract_pdf(pdf_path: Path, *, on_page_done=None) -> str:
    """Extract toàn bộ PDF → markdown đánh số ---SLIDE_N---.

    Args:
        pdf_path: đường dẫn file PDF.
        on_page_done: callback(page_index, total_pages) gọi sau mỗi trang xong (cho progress).

    Returns:
        Markdown string với format ---SLIDE_N--- cho mỗi trang.
    """
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    n = doc.page_count
    doc.close()

    logger.info("[Extract] %s: %d trang, OCR song song (%d)...", pdf_path.name, n, settings.llm_concurrency)

    pages: list[dict] = [{}] * n

    with ThreadPoolExecutor(max_workers=settings.llm_concurrency) as pool:
        futures = {pool.submit(_ocr_one_page, pdf_path, i): i for i in range(n)}
        for future in as_completed(futures):
            result = future.result()
            idx = result["page"]
            pages[idx] = result
            if on_page_done:
                on_page_done(idx, n)
            logger.info("[OCR] Trang %d/%d xong.", idx + 1, n)

    md = "".join(f"\n\n---SLIDE_{i + 1}---\n\n{p['text']}\n" for i, p in enumerate(pages))

    total_in = sum(p.get("in", 0) for p in pages)
    total_out = sum(p.get("out", 0) for p in pages)
    empty = sum(1 for p in pages if len(p.get("text", "").strip()) < 5)

    logger.info(
        "[Extract] Xong | %d+%d tokens | %d/%d trang trống",
        total_in, total_out, empty, n,
    )

    return md
