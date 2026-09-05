"""Cấu hình tập trung cho slide2reveal — đọc từ .env qua pydantic-settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Beeknoee credentials ---
    beeknoee_api_key: str = Field(default="", alias="BEEKNOEE_API_KEY")
    beeknoee_base_url: str = Field(
        default="https://platform.beeknoee.com/api/v1", alias="BEEKNOEE_BASE_URL"
    )

    # --- Models ---
    ocr_vision_model: str = Field(default="google/gemini-2.5-flash", alias="OCR_VISION_MODEL")
    transform_model: str = Field(default="google/gemini-2.5-flash", alias="TRANSFORM_MODEL")

    # --- Render ---
    render_dpi: int = Field(default=200, alias="RENDER_DPI")
    slide_image_max_w: int = Field(default=1920, alias="SLIDE_IMAGE_MAX_W")
    slide_image_max_h: int = Field(default=1080, alias="SLIDE_IMAGE_MAX_H")

    # --- Concurrency ---
    llm_concurrency: int = Field(default=5, alias="LLM_CONCURRENCY")
    tts_concurrency: int = Field(default=4, alias="TTS_CONCURRENCY")

    # --- TTS ---
    # NCC TTS hoạt động: "google" | "beeknoee". Chỉ là mặc định seed; catalog giọng + per-voice
    # là cấu hình runtime (app/core/tts_config.py). Đổi runtime không cần restart.
    tts_default_provider: str = Field(default="beeknoee", alias="TTS_DEFAULT_PROVIDER")
    tts_default_voice: str = Field(default="zephyr", alias="TTS_DEFAULT_VOICE")
    # Model Beeknoee dùng cho giọng không khai model riêng (OpenAI-compat /audio/speech).
    beeknoee_tts_model: str = Field(
        default="google/gemini-2.5-flash-tts", alias="BEEKNOEE_TTS_MODEL"
    )
    # Ngưỡng an toàn cho Google synthesize_speech (bytes); cắt câu trên ngưỡng này.
    tts_max_input_bytes: int = Field(default=4500, alias="TTS_MAX_INPUT_BYTES")
    # Định giá: đ/ký tự (vốn vendor) + markup thu user.
    tts_vnd_per_char: float = Field(default=0.825, alias="TTS_VND_PER_CHAR")
    tts_vendor_markup: float = Field(default=1.2, alias="TTS_VENDOR_MARKUP")
    # Nhất quán tông giọng trên mọi fragment: tốc độ đọc (speed), cao độ (pitch — Google native),
    # ngôn ngữ ép buộc. dùng chung để mọi clip nghe như CÙNG một người đọc.
    tts_speed: float = Field(default=1.0, alias="TTS_SPEED")
    tts_pitch: float = Field(default=0.0, alias="TTS_PITCH")
    tts_language: str = Field(default="vi-VN", alias="TTS_LANGUAGE")
    # Retry lỗi NHẤT THỜI (Connection error / 502 / 429 / timeout): TTS dễ bị nghẽn hoặc proxy
    # lỗi thoáng qua; retry có backoff giúp audio đầy đủ thay vì bỏ trống.
    tts_retry_attempts: int = Field(default=4, alias="TTS_RETRY_ATTEMPTS")
    tts_retry_base_delay: float = Field(default=0.6, alias="TTS_RETRY_BASE_DELAY")
    # Timeout mỗi call TTS (giây) — ngắn hơn LLM vì TTS trả nhanh; tránh treo lâu khi provider câm.
    tts_timeout_sec: float = Field(default=60, alias="TTS_TIMEOUT_SEC")

    # --- Timeout ---
    llm_timeout_sec: float = Field(default=120, alias="LLM_TIMEOUT_SEC")

    # --- Reveal.js ---
    revealjs_theme: str = Field(default="white", alias="REVEALJS_THEME")
    revealjs_transition: str = Field(default="slide", alias="REVEALJS_TRANSITION")
    revealjs_transition_speed: str = Field(default="default", alias="REVEALJS_TRANSITION_SPEED")

    # --- Paths ---
    jobs_dir: Path = Field(default=BASE_DIR / "jobs", alias="JOBS_DIR")


settings = Settings()
