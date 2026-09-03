"""LLM client tối giản cho slide2reveal — Vision OCR + Text generation.

Dùng LangChain ChatOpenAI trỏ vào Beeknoee (OpenAI-compatible proxy).
Rút gọn từ spro/app/core/llm_client.py: bỏ multi-provider fallback, observability,
usage tracking — giữ lại phần core hoạt động.
"""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# Cache chat models
_chat_models: dict[tuple, Any] = {}


def _get_chat_model(model: str, *, json_mode: bool = False):
    """Return cached LangChain ChatOpenAI for the given model."""
    from langchain_openai import ChatOpenAI

    key = (model, json_mode)
    if key not in _chat_models:
        model_kwargs = {}
        if json_mode:
            model_kwargs["response_format"] = {"type": "json_object"}

        _chat_models[key] = ChatOpenAI(
            model=model,
            api_key=settings.beeknoee_api_key,
            base_url=settings.beeknoee_base_url,
            temperature=0.1,
            timeout=settings.llm_timeout_sec,
            max_retries=2,
            model_kwargs=model_kwargs,
            use_responses_api=False,
            streaming=False,
        )
        logger.info("[LLM] Chat model created: %s (json_mode=%s)", model, json_mode)
    return _chat_models[key]


def _message_text(message) -> str:
    """Extract plain text from AIMessage content."""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") in (None, "text"):
                    parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "".join(parts)
    return "" if content is None else str(content)


def _usage(message) -> tuple[int, int]:
    """(input_tokens, output_tokens) from AIMessage."""
    usage = getattr(message, "usage_metadata", None) or {}
    return int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)


def call_llm_vision(prompt: str, image_b64: str, *, mime_type: str = "image/png") -> tuple[str, int, int]:
    """Vision call: gửi ảnh base64 + prompt → (text, tok_in, tok_out).

    Dùng cho OCR từng trang PDF.
    """
    from langchain_core.messages import HumanMessage

    llm = _get_chat_model(settings.ocr_vision_model, json_mode=False)
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {"type": "image", "source_type": "base64", "data": image_b64, "mime_type": mime_type},
        ]
    )
    response = llm.invoke([message])
    tok_in, tok_out = _usage(response)
    text = _message_text(response).strip()
    return text, tok_in, tok_out


def call_llm_text(system_prompt: str, user_content: str, *, model: str | None = None) -> str:
    """Text completion: system + user prompt → response text.

    Dùng cho bước transform markdown → Reveal.js HTML.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    resolved_model = model or settings.transform_model
    llm = _get_chat_model(resolved_model, json_mode=False)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]

    for attempt in range(3):
        response = llm.invoke(messages)
        text = _message_text(response).strip()
        if text:
            return text
        logger.warning("[LLM] Empty response (attempt %d/3), retrying...", attempt + 1)

    raise RuntimeError(f"LLM returned empty response after 3 retries (model={resolved_model})")
