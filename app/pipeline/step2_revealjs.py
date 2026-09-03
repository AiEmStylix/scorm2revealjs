"""BƯỚC 2 — Assemble: ghép sections HTML vào template Reveal.js hoàn chỉnh.

Reveal.js 6.0.1 qua CDN (jsDelivr). Plugins: MathJax3 (LaTeX), Highlight (code).
Template self-contained — mở file HTML là chạy được trên trình duyệt.
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# CDN base cho Reveal.js 6.0.1
_REVEALJS_CDN = "https://cdn.jsdelivr.net/npm/reveal.js@6.0.1"


def build_revealjs_html(
    title: str,
    sections_html: str,
    *,
    theme: str | None = None,
    transition: str | None = None,
    transition_speed: str | None = None,
) -> str:
    """Ghép sections HTML vào template Reveal.js hoàn chỉnh.

    Args:
        title: tiêu đề bài giảng (hiện ở <title> + slide đầu nếu muốn).
        sections_html: các <section>...</section> từ step1_transform.
        theme: tên theme Reveal.js (mặc định từ settings).
        transition: hiệu ứng chuyển cảnh (mặc định từ settings).
        transition_speed: tốc độ chuyển cảnh (mặc định từ settings).

    Returns:
        Full HTML5 document string.
    """
    resolved_theme = theme or settings.revealjs_theme
    resolved_transition = transition or settings.revealjs_transition
    resolved_transition_speed = transition_speed or settings.revealjs_transition_speed

    logger.info(
        "[Reveal.js] Assembling HTML (theme=%s, transition=%s)...",
        resolved_theme,
        resolved_transition,
    )

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title}</title>
<link rel="stylesheet" href="{_REVEALJS_CDN}/dist/reveal.css"/>
<link rel="stylesheet" href="{_REVEALJS_CDN}/dist/theme/{resolved_theme}.css"/>
<style>
  /* Custom overrides for Vietnamese slide content */
  .reveal {{
    font-family: 'Segoe UI', Roboto, 'Noto Sans', Arial, sans-serif;
  }}
  .reveal h1, .reveal h2, .reveal h3 {{
    text-transform: none;
    font-weight: 700;
  }}
  .reveal h2 {{
    font-size: 1.6em;
    margin-bottom: 0.5em;
  }}
  .reveal h3 {{
    font-size: 1.2em;
    color: #555;
  }}
  .reveal p {{
    font-size: 0.85em;
    line-height: 1.6;
  }}
  .reveal ul, .reveal ol {{
    font-size: 0.82em;
    text-align: left;
    display: block;
  }}
  .reveal li {{
    margin-bottom: 0.4em;
    line-height: 1.5;
  }}
  .reveal table {{
    border-collapse: collapse;
    margin: 0.8em auto;
    font-size: 0.75em;
  }}
  .reveal table th,
  .reveal table td {{
    border: 1px solid #ccc;
    padding: 8px 14px;
    text-align: left;
  }}
  .reveal table th {{
    background: #f0f0f0;
    font-weight: 600;
  }}
  .reveal .text-muted {{
    color: #999;
    font-style: italic;
  }}
  /* MathJax: đảm bảo công thức không bị crop */
  .reveal .MathJax {{
    font-size: 100% !important;
  }}
  /* Slide counter */
  .reveal .slide-number {{
    font-size: 14px;
    color: #666;
  }}
  /* Prevent text overflow by enabling scroll */
  .reveal .slides section {{
    max-height: 100vh;
    overflow-y: auto !important;
    overflow-x: hidden;
    padding-bottom: 20px;
  }}
</style>
</head>
<body>
<div class="reveal">
  <div class="slides">
{sections_html}
  </div>
</div>

<script src="{_REVEALJS_CDN}/dist/reveal.js"></script>
<script src="{_REVEALJS_CDN}/dist/plugin/math.js"></script>
<script src="{_REVEALJS_CDN}/dist/plugin/highlight.js"></script>
<script>
  Reveal.initialize({{
    hash: true,
    slideNumber: true,
    transition: '{resolved_transition}',
    transitionSpeed: '{resolved_transition_speed}',
    center: false,
    math: {{
      mathjax: 'https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js',
      config: 'TeX-AMS_HTML-full'
    }},
    plugins: [RevealMath.MathJax3, RevealHighlight]
  }});
</script>
</body>
</html>"""
