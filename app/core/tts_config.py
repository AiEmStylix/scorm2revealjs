"""Cấu hình TTS runtime: catalog giọng + resolve(voice_id).

Rút gọn từ spro/app/core/tts_config.py:
- Giữ nguyên nguyên tắc: NCC + catalog giọng là cấu hình runtime (không hardcode trong .env),
  1 điểm dispatch chọn provider theo `active_provider()`, và resolve() tách "đọc cấu hình"
  khỏi "gọi TTS".
- Khác spro: không có DB / snapshot cache / validate(). Ở đây catalog là hằng số trong
  module, seed từ env; resolve() vẫn nghiêm ngặt: voice_id có giá trị mà mất khỏi catalog
  của provider đang hoạt động → raise (không lặng lẽ đọc giọng khác).
"""

import logging

from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

# Beeknoee là proxy OpenAI-compatible; TTS đi qua POST /audio/speech với model này.
_BEEKNOEE_MODEL = settings.beeknoee_tts_model


class TTSVoice(BaseModel):
    """Một giọng trong catalog của một provider.

    - key: voice_id ngắn gọn mà caller dùng (vd "zephyr").
    - provider: thuộc provider nào ("google" | "beeknoee").
    - voice: tên voice thật trên provider (vd "vi-VN-Chirp3-HD-Zephyr").
    - model: chỉ bắt buộc cho beeknoee (model /audio/speech); google native để None.
    """

    key: str
    display_name: str
    provider: str
    voice: str
    model: str | None = None


# Catalog theo provider. Google Chirp3-HD là giọng chung; cùng tên voice chạy trên
# cả Google native (model=None) lẫn Beeknoee (model=google/gemini-2.5-flash-tts).
_CATALOG: dict[str, list[TTSVoice]] = {
    "beeknoee": [
        TTSVoice(
            key="zephyr",
            display_name="Zephyr (Nữ)",
            provider="beeknoee",
            voice="vi-VN-Chirp3-HD-Zephyr",
            model=_BEEKNOEE_MODEL,
        ),
        TTSVoice(
            key="kore",
            display_name="Kore (Nữ)",
            provider="beeknoee",
            voice="vi-VN-Chirp3-HD-Kore",
            model=_BEEKNOEE_MODEL,
        ),
        TTSVoice(
            key="charon",
            display_name="Charon (Nam)",
            provider="beeknoee",
            voice="vi-VN-Chirp3-HD-Charon",
            model=_BEEKNOEE_MODEL,
        ),
    ],
    "google": [
        TTSVoice(
            key="zephyr",
            display_name="Zephyr (Nữ)",
            provider="google",
            voice="vi-VN-Chirp3-HD-Zephyr",
            model=None,
        ),
        TTSVoice(
            key="kore",
            display_name="Kore (Nữ)",
            provider="google",
            voice="vi-VN-Chirp3-HD-Kore",
            model=None,
        ),
        TTSVoice(
            key="charon",
            display_name="Charon (Nam)",
            provider="google",
            voice="vi-VN-Chirp3-HD-Charon",
            model=None,
        ),
    ],
}


class TTSConfig:
    """Cấu hình TTS hoạt động + resolve(voice_id) → (provider, voice, model)."""

    def __init__(
        self,
        provider: str,
        default_voice: str,
        voices: dict[str, list[TTSVoice]],
    ) -> None:
        self.provider = provider
        self.default_voice = default_voice
        self.voices = voices

    def active_provider(self) -> str:
        """Provider đang hoạt động — chính là nhánh của hàm dispatch _synthesize()."""
        return self.provider

    def all_voices(self, provider: str | None = None) -> list[TTSVoice]:
        pool = self.voices.get(provider or self.provider, [])
        return list(pool)

    def resolve(self, voice_id: str | None = None) -> tuple[str, str, str | None]:
        """voice_id (KEY) → (provider, voice, model).

        Lệch/None → giọng mặc định. NHƯNG nếu voice_id có giá trị mà không còn trong
        catalog của provider đang hoạt động → raise (user trả tiền giọng A phải nghe A).
        """
        pool = self.voices.get(self.provider, [])
        vid = (voice_id or self.default_voice).strip()
        hit = next((v for v in pool if v.key == vid), None)
        if hit is None:
            if voice_id and voice_id.strip():
                raise ValueError(
                    f"Giọng '{voice_id}' không tồn tại trong catalog provider '{self.provider}'."
                )
            if not pool:
                raise ValueError(f"Provider '{self.provider}' không có giọng nào trong catalog.")
            hit = pool[0]
        return hit.provider, hit.voice, hit.model


_default_config: TTSConfig | None = None


def get_config() -> TTSConfig:
    """Snapshot cấu hình TTS hiện tại (đọc 1 lần mỗi tiến trình).

    Không có DB nên không cần refresh; giữ chữ ký giống spro để dễ nâng cấp lên runtime
    sau này nếu project thêm DB.
    """
    global _default_config
    if _default_config is None:
        provider = settings.tts_default_provider
        if provider not in _CATALOG:
            logger.warning("[TTS] Provider '%s' không hợp lệ → mặc định beeknoee.", provider)
            provider = "beeknoee"
        pool = _CATALOG[provider]
        default_voice = settings.tts_default_voice
        if not any(v.key == default_voice for v in pool):
            default_voice = pool[0].key
            logger.warning(
                "[TTS] default_voice '%s' vắng trong catalog '%s' → '%s'.",
                settings.tts_default_voice, provider, default_voice,
            )
        _default_config = TTSConfig(provider=provider, default_voice=default_voice, voices=_CATALOG)
    return _default_config


def resolve(voice_id: str | None = None) -> tuple[str, str, str | None]:
    """Convenience: (provider, voice, model) cho voice_id."""
    return get_config().resolve(voice_id)


def active_provider() -> str:
    """Convenience: provider đang hoạt động."""
    return get_config().active_provider()
