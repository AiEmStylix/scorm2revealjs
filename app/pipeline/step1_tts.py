"""BƯỚC 1.5 — TTS: từng fragment của từng slide → audio WAV + voice_manifest.json.

Rút gọn từ spro/app/pipeline/step4_tts.py (synthesize_section):
- Điểm khác spro: không section/DB/MinIO — đầu vào là sections.html của Reveal.js, mỗi
  "dòng" (fragment) là 1 clip nghe khi fragment hiện ra (đồng bộ từng dòng).
- Idempotency theo content-hash của dòng + voice: file audio đã tồn tại & chưa đổi giọng/
  nội dung thì tái dùng (không synth, không trừ tiền).
- Module này ĐỌC CẤU HÌNH (resolve) rồi GỌI TTS — hai việc tách bạch, giống spro.
"""

import hashlib
import json
import logging
import re
from pathlib import Path

from app.core import tts_engine
from app.core.config import settings
from app.core.tts_config import resolve
from app.core.tts_text import to_tts_text
from app.core.usage import TTSUsage

logger = logging.getLogger(__name__)

_AUDIO_SUBDIR = "audio"


def _code_text(el) -> str:
    """Đọc nội dung MÃ (thẻ <code>/<pre>) LITERAL — không biến `++`, `#include <...>` thành chữ vô nghĩa.

    Khác lời giảng thuần: mã nguồn giữ nguyên chữ-số + ký hiệu, chỉ gỡ code fence/LaTeX thô.
    """
    text = el.get_text(separator="", strip=False)
    text = re.sub(r"```[a-zA-Z]*", " ", text)
    text = text.replace(r"\(", " ").replace(r"\)", " ").replace(r"\[", " ").replace(r"\]", " ")
    text = re.sub(r"[\\{}]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_text(el) -> str:
    """Nội dung text của 1 element, ĐÃ DỌN sẵn cho TTS (đọc đúng công thức, tiếng Việt).

    Đoạn mã (thẻ <code>/<pre>) đọc literal — không đổi ký hiệu thành chữ.
    Trả text ở dạng CUỐI (nội dung sẽ gửi cho TTS) → gọi engine với normalize=False.
    """
    if el.name in ("code", "pre") or el.find(["code", "pre"]):
        return _code_text(el)
    text = el.get_text(separator=" ", strip=True)
    return to_tts_text(text)


def extract_slide_lines(sections_html: str) -> list[dict]:
    """Parse sections.html → list slide. Mỗi slide: {index, fragments, lines[]}.

    - lines = các element có class "fragment" theo thứ tự DOM (đúng thứ tự Reveal hiện dần).
    - Nếu slide không có fragment nào → 1 dòng cấp slide (đọc toàn slide).
    - Mỗi line["text"] là text SẼ ĐỌC (đã dọn toán/tiếng Việt) — dùng cho hash + manifest.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(sections_html, "html.parser")
    slides: list[dict] = []
    for sec in soup.find_all("section"):
        frags = sec.find_all(class_="fragment")
        if frags:
            lines = [{"text": _extract_text(f), "is_fragment": True} for f in frags]
            fragments = True
        else:
            text = _extract_text(sec)
            lines = [{"text": text, "is_fragment": False}] if text else []
            fragments = False
        slides.append(
            {"index": len(slides), "fragments": fragments, "lines": lines}
        )
    return slides


def _audio_filename(provider: str, voice: str, model: str | None, text: str) -> str:
    """Tên audio (relative đến audio_dir) theo content-hash của (provider, voice, model, text)."""
    key = f"{provider}|{voice}|{model or ''}|{text}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return f"{h}.wav"


def _synth_task_factory(audio_dir: Path, provider: str, voice: str, model: str | None, usage: TTSUsage | None):
    """Tạo callable chạy mỗi task nội dung ĐỘC NHẤT (filename, text, slide) → (filename | None,).

    Mỗi nội dung trùng chỉ synth ĐÚNG 1 lần (dedupe) — tránh gửi yêu cầu y hệt song song
    lên Beeknoee (409 Conflict "duplicate") và giảm tải provider.
    """

    def task(item: tuple[str, str, int]):
        filename, text, si = item
        full = audio_dir / filename
        try:
            if not full.exists():
                # text đã được dọn sẵn trong extract_slide_lines → normalize=False (tránh dọn 2 lần).
                wav = tts_engine.synthesize(text, provider, voice, model, normalize=False)
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_bytes(wav)
            if usage:
                usage.record(text, provider, model, voice, slide=si, ok=True)
            return filename
        except Exception as e:  # noqa: BLE001 - 1 dòng lỗi không kéo sập cả bài
            err = str(e)
            # Rút gọn lỗi dài (Cloudflare/502 trả nguyên trang HTML) — chỉ ghi đầu chuỗi.
            logger.warning("[TTS] %s lỗi: %s", filename[:12], err[:220])
            if usage:
                usage.record(text, provider, model, voice, slide=si, ok=False, error=err)
            return None

    return task


def synthesize_tts(
    sections_html: str,
    audio_dir: Path,
    *,
    voice_id: str | None = None,
    usage: TTSUsage | None = None,
) -> dict:
    """Sinh TTS cho mọi dòng (fragment) của mọi slide → voice_manifest.

    DEDUPE: các dòng trùng nội dung (cùng provider+voice+text → cùng hash tên file) chỉ synth
    MỘT lần rồi dùng chung file — tránh 409 duplicate + giảm tải + không tính phí trùng.

    Returns:
        Manifest dict dùng để nhúng vào HTML (preview + SCORM):
        {"provider", "voice", "voice_id", "slides": [
            {"index", "fragments", "lines": [{"idx", "text", "audio"}]}
        ]}
    """
    provider, voice, model = resolve(voice_id)
    slides = extract_slide_lines(sections_html)

    # Đầu tiên: ánh xạ (slide,line) → filename; gom filename → [(slide,line)...]; filename → text.
    slot: dict[tuple[int, int], str] = {}
    texts: dict[str, str] = {}
    jobs: dict[str, list[tuple[int, int]]] = {}
    for si, slide in enumerate(slides):
        for li, line in enumerate(slide["lines"]):
            if line["text"]:
                filename = _audio_filename(provider, voice, model, line["text"])
                slot[(si, li)] = filename
                texts.setdefault(filename, line["text"])
                jobs.setdefault(filename, []).append((si, li))
            else:
                line["audio"] = None

    filenames = list(jobs.keys())  # NỘI DUNG ĐỘC NHẤT
    logger.info(
        "[TTS] %d slide / %d dòng (dedupe → %d nội dung duy nhất) | provider=%s voice=%s concurrency=%d",
        len(slides), sum(len(v) for v in jobs.values()), len(filenames),
        provider, voice, settings.tts_concurrency,
    )

    tasks = [(fn, texts[fn], jobs[fn][0][0]) for fn in filenames]
    fn = _synth_task_factory(audio_dir, provider, voice, model, usage)
    results = tts_engine.map_ordered_tasks(tasks, fn)
    # Ghi nhớ các filename synth THÀNH CÔNG để gán lại cho mọi dòng trùng.
    ok_files = {fn for fn, _res in zip(filenames, results) if _res}

    for (si, li), filename in slot.items():
        slides[si]["lines"][li]["audio"] = f"{_AUDIO_SUBDIR}/{filename}" if filename in ok_files else None

    manifest = {
        "provider": provider,
        "voice": voice,
        "voice_id": voice_id or settings.tts_default_voice,
        "slides": slides,
    }
    return manifest


def write_manifest(manifest: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
