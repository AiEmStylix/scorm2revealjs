"""TTS engine: 1 điểm dispatch + xử lý text dài + concurrency + idempotency.

Rút gọn từ spro/app/pipeline/step4_tts.py:
- 1 điểm dispatch `_synthesize(text, provider, voice, model)` trả WAV bytes — contract
  giống nhau mọi provider (Google native vs Beeknoee OpenAI-compat).
- Text quá dài → cắt theo câu / từ, nối lại WAV (soundfile + numpy).
- Không fallback giữa provider/giọng: mỗi model cho âm khác nhau; provider trả lỗi là
  raise luôn, không tự đổi giọng ngầm.
"""

import io
import logging
import random
import re
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from app.core.config import settings
from app.core.tts_text import to_tts_text

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = ("google", "beeknoee")

# Chuỗi con cho biết đây là LỖI NHẤT THỜI (retry được) — proxy/Cloudflare/nghẽn mạng.
_TRANSIENT_MARKERS = (
    "connection error", "connection reset", "timed out", "timeout", "read timeout",
    "rate limit", "429", "502", "503", "504", "bad gateway", "service unavailable",
    "server error", "5 0 2", "5 0 3", "5 0 4", "temporarily", "overloaded", "retry",
    "409", "duplicate", "conflict",  # yêu cầu trùng đang xử lý → wait & retry
)


def _is_transient(exc: Exception) -> bool:
    """True nếu lỗi ĐÁNG retry (mạng/proxy/nghẽn) — không retry lỗi cấu hình/giọng/400."""
    msg = str(exc).lower()
    if not msg:
        return False
    # Cloudflare/Beeknoee trả nguyên trang HTML lỗi → vẫn là lỗi proxy thoáng qua.
    if "<!doctype" in msg or "doctype html" in msg:
        return True
    return any(m in msg for m in _TRANSIENT_MARKERS)


def _call_once(stripped: str, provider: str, voice: str, model: str | None) -> bytes:
    if provider == "google":
        return _synthesize_google(stripped, voice)
    return _synthesize_beeknoee(stripped, voice, model)


def synthesize(
    text: str,
    provider: str,
    voice: str,
    model: str | None = None,
    *,
    normalize: bool = True,
) -> bytes:
    """Trả WAV bytes cho (text, provider, voice).

    Retry lỗi NHẤT THỜI (Connection error / 502 / 429 / timeout) với backoff + jitter, vì TTS
    qua proxy (Beeknoee/Cloudflare) rất hay bị nghẽn/502 thoáng qua. Không retry lỗi cấu hình.

    Args:
        text: nội dung cần đọc.
        provider: "google" | "beeknoee".
        voice: tên voice trên provider.
        model: model TTS (beeknoee bắt buộc).
        normalize: True → chạy `to_tts_text` (dọn LaTeX/toán → tiếng Việt). False → text đã
            được caller dọn sẵn (tránh dọn 2 lần và giữ đúng ngữ nghĩa).

    Raises:
        ValueError: text rỗng hoặc provider không hợp lệ.
    """
    # Bình thường hoá lần cuối (an toàn nếu caller đưa text thô có LaTeX/ký hiệu toán):
    # dọn cho TTS đọc tiếng Việt mạch lạc, tránh model tự chuyển sang tiếng Anh.
    stripped = to_tts_text(text) if normalize else (text or "").strip()
    if not stripped:
        raise ValueError("Không thể TTS chuỗi rỗng.")
    if provider not in _SUPPORTED_PROVIDERS:
        raise ValueError(f"Provider TTS không hợp lệ: '{provider}'.")

    if len(stripped.encode("utf-8")) > settings.tts_max_input_bytes:
        return _synthesize_long(stripped, provider, voice, model, normalize=False)

    attempts = max(1, settings.tts_retry_attempts)
    base = max(0.1, settings.tts_retry_base_delay)
    for attempt in range(attempts):
        try:
            return _call_once(stripped, provider, voice, model)
        except Exception as e:
            if attempt < attempts - 1 and _is_transient(e):
                delay = base * (2 ** attempt) + random.uniform(0, base)
                logger.warning(
                    "[TTS] lỗi nhẹ lần %d/%d (%s) → retry sau %.1fs",
                    attempt + 1, attempts, type(e).__name__, delay,
                )
                time.sleep(delay)
                continue
            raise


# ---------------------------------------------------------------------------
# Google Cloud TTS native
# ---------------------------------------------------------------------------
def _synthesize_google(text: str, voice: str) -> bytes:
    """Google Cloud Text-to-Speech, output LINEAR16 (WAV).

    Dùng transport="rest" thay gRPC — chìa khóa tránh crash fork khi sau đó chạy ffmpeg/
    subprocess (gRPC giữ thread poller nền → vi phạm fork-safety).
    """
    try:
        from google.cloud import texttospeech
    except ImportError as e:  # pragma: no cover - trae hướng dẫn rõ
        raise RuntimeError(
            "Google TTS chưa cài. Chạy: uv add google-cloud-texttospeech "
            "và đặt GOOGLE_APPLICATION_CREDENTIALS."
        ) from e

    client = texttospeech.TextToSpeechClient(transport="rest")
    lang_code = settings.tts_language  # "vi-VN" — ép ngôn ngữ tránh đọc nhầm tiếng Anh.

    req = texttospeech.SynthesizeSpeechRequest(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(language_code=lang_code, name=voice),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=24000,
            speaking_rate=settings.tts_speed,
            pitch=settings.tts_pitch,
        ),
    )
    resp = client.synthesize_speech(request=req)
    return resp.audio_content


# ---------------------------------------------------------------------------
# Beeknoee (OpenAI-compatible /audio/speech)
# ---------------------------------------------------------------------------
def _synthesize_beeknoee(text: str, voice: str, model: str | None) -> bytes:
    """OpenAI-compat client.audio.speech.create → WAV bytes. Cùng key với LLM."""
    from openai import OpenAI

    resolved_model = model or settings.beeknoee_tts_model
    client = OpenAI(
        api_key=settings.beeknoee_api_key,
        base_url=settings.beeknoee_base_url,
        timeout=settings.tts_timeout_sec,
        # QUAN TRỌNG: max_retries=0 — mỗi lỗi (502/429) trả về LẬP TỨC, không để SDK tự retry
        # với backoff 60s (gây treo hàng phút mỗi dòng). Việc retry do vòng ngoài `synthesize()`
        # đảm nhiệm với backoff ngắn (0.7s/1.4s/2.8s).
        max_retries=0,
    )
    resp = client.audio.speech.create(
        model=resolved_model,
        voice=voice,
        input=text,
        response_format="wav",
        speed=settings.tts_speed,
        # Ép ngôn ngữ tiếng Việt cho Gemini TTS (tránh tự đoán → đọc tiếng Anh).
        extra_body={"language": settings.tts_language.split("-")[0]},
    )
    data = getattr(resp, "content", None)
    if data is None:
        data = resp.read()
    return data


# ---------------------------------------------------------------------------
# Text dài: cắt theo câu / từ rồi nối WAV
# ---------------------------------------------------------------------------
def _split_by_sentences(text: str, limit: int) -> list[str]:
    """Cắt text theo ranh giới câu, mỗi đoạn ≤ limit bytes; câu quá dài thì cắt theo từ."""
    parts = re.split(r"(?<=[.!?…])\s+", text)
    groups: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part.encode("utf-8")) <= limit:
            groups.append(part)
        else:
            groups.extend(_split_by_words(part, limit))
    return groups


def _split_by_words(text: str, limit: int) -> list[str]:
    """Nếu 1 câu vẫn quá dài → cắt theo từ, mỗi đoạn ≤ limit bytes."""
    groups: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for word in text.split():
        wl = len(word.encode("utf-8")) + 1
        if cur and cur_len + wl > limit:
            groups.append(" ".join(cur))
            cur, cur_len = [], 0
        cur.append(word)
        cur_len += wl
    if cur:
        groups.append(" ".join(cur))
    return groups


def _synthesize_long(
    text: str, provider: str, voice: str, model: str | None, *, normalize: bool = True
) -> bytes:
    """TTS text dài: synth từng đoạn rồi nối WAV lại (cùng format)."""
    parts = _split_by_sentences(text, settings.tts_max_input_bytes)
    if len(parts) == 1:
        return synthesize(parts[0], provider, voice, model, normalize=normalize)
    wavs = [synthesize(p, provider, voice, model, normalize=False) for p in parts]
    return _concat_wavs(wavs)


def _concat_wavs(wavs: list[bytes]) -> bytes:
    """Nối các WAV (cùng sample-rate, mono, PCM_16) thành 1 WAV bằng soundfile + numpy."""
    import numpy as np
    import soundfile as sf

    chunks: list[np.ndarray] = []
    sr: int | None = None
    for w in wavs:
        data, s = sf.read(io.BytesIO(w), dtype="float32")
        if data.ndim == 2:
            data = data.mean(axis=1)
        if sr is None:
            sr = int(s)
        chunks.append(data)

    arr = np.concatenate(chunks)
    buf = io.BytesIO()
    sf.write(buf, arr, sr or 24000, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Concurrency giới hạn, giữ thứ tự (map_ordered)
# ---------------------------------------------------------------------------
def map_ordered_tasks(items: list, fn, max_workers: int | None = None) -> list:
    """Chạy fn(item) song song nhưng trả kết quả theo thứ tự `items`.

    Mỗi task là 1 item; fn(item) → result. Giữ thứ tự input — quan trọng cho manifest.
    """
    workers = max_workers or settings.tts_concurrency
    if len(items) <= 1:
        return [fn(it) for it in items]

    futures: dict[Future, int] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, it in enumerate(items):
            futures[pool.submit(fn, it)] = i
        results: list = [None] * len(items)
        for fut in as_completed(futures):
            idx = futures[fut]
            results[idx] = fut.result()
    return results
