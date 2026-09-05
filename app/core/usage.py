"""Ghi sổ ký tự TTS + chi phí (tách giá thu user / giá vốn vendor).

Rút gọn từ spro/app/core/usage.py: bỏ DB, chỉ accumulate trong bộ nhớ và serialize ra JSON
theo từng job. Giữ nguyên tắc:
- Ký tự THẬT = len(text) mỗi lần synth thành công.
- Giá thu user (markup) = chars × TTS_VND_PER_CHAR × TTS_VENDOR_MARKUP.
- Giá vốn vendor (không markup) = chars × TTS_VND_PER_CHAR.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TTSLine:
    section: int | None = None
    slide: int | None = None
    chars: int = 0
    provider: str = ""
    model: str | None = None
    voice: str = ""
    ok: bool = False
    error: str | None = None


@dataclass
class TTSUsage:
    """Tích lũy ký tự/chi phí TTS trong một job."""

    lines: list[TTSLine] = field(default_factory=list)

    def record(
        self,
        text: str,
        provider: str,
        model: str | None,
        voice: str,
        *,
        slide: int | None = None,
        ok: bool = True,
        error: str | None = None,
    ) -> None:
        self.lines.append(
            TTSLine(
                slide=slide,
                chars=len(text),
                provider=provider,
                model=model,
                voice=voice,
                ok=ok,
                error=error,
            )
        )

    @property
    def synthesized_chars(self) -> int:
        """Tổng ký tự đã đọc THÀNH CÔNG."""
        return sum(l.chars for l in self.lines if l.ok)

    def cost_vendor_vnd(self, char_price_vnd: float | None = None) -> int:
        price = char_price_vnd if char_price_vnd is not None else settings.tts_vnd_per_char
        return round(self.synthesized_chars * price)

    def cost_charged_vnd(self) -> int:
        """Giá thu user (có markup)."""
        return round(self.synthesized_chars * settings.tts_vnd_per_char * settings.tts_vendor_markup)

    @property
    def failed_lines(self) -> list[TTSLine]:
        return [l for l in self.lines if not l.ok]

    @property
    def ok_lines(self) -> list[TTSLine]:
        return [l for l in self.lines if l.ok]

    def to_dict(self) -> dict:
        total = self.synthesized_chars
        return {
            "chars": total,
            "cost_vendor_vnd": self.cost_vendor_vnd(),
            "cost_charged_vnd": self.cost_charged_vnd(),
            "vnd_per_char": settings.tts_vnd_per_char,
            "vendor_markup": settings.tts_vendor_markup,
            "provider": settings.tts_default_provider,
            "ok_lines": len(self.ok_lines),
            "failed": len(self.failed_lines),
            "lines": [
                {
                    "slide": l.slide,
                    "chars": l.chars,
                    "provider": l.provider,
                    "model": l.model,
                    "voice": l.voice,
                    "ok": l.ok,
                    "error": (l.error[:200] if l.error else None),
                }
                for l in self.lines
            ],
        }

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(
            "[TTS usage] %d ký tự | vốn %dđ | thu %dđ",
            self.synthesized_chars,
            self.cost_vendor_vnd(),
            self.cost_charged_vnd(),
        )
