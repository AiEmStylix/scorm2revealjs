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

    # --- Timeout ---
    llm_timeout_sec: float = Field(default=120, alias="LLM_TIMEOUT_SEC")

    # --- Reveal.js ---
    revealjs_theme: str = Field(default="white", alias="REVEALJS_THEME")

    # --- Paths ---
    jobs_dir: Path = Field(default=BASE_DIR / "jobs", alias="JOBS_DIR")


settings = Settings()
