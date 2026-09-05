# slide2reveal

Chuyển đổi file PDF slide bài giảng thành bài trình chiếu **Reveal.js** tương tác, đóng gói **SCORM 1.2** để import vào LMS (Moodle, ...).

## Pipeline

1. **Extract** — Vision OCR (Gemini) đọc từng trang PDF → Markdown
2. **Transform** — LLM chuyển Markdown → Reveal.js HTML sections
3. **TTS** — Sinh giọng đọc cho từng fragment (mỗi dòng hiện dần) qua Beeknoee/Google; đồng bộ phát nhạc khi dòng hiện ra
4. **Preview** — Xem trực tiếp trên web bằng Reveal.js 6.0.1
5. **SCORM Pack** — Đóng gói `imsmanifest.xml` + `index.html` + `scorm_api.js` + `audio/` → `.zip`

> Giọng đọc đồng bộ theo từng dòng: Reveal.js `fragmentshown` → `<audio>` phát đúng clip của dòng vừa hiện; đi dòng trước/sau tự dừng clip đang chạy. Cấu hình giọng ở `app/core/tts_config.py` (default beeknoee).

## Quick Start

```bash
# 1. Clone & cài đặt
cd slide2reveal
cp .env.example .env
# Điền BEEKNOEE_API_KEY vào .env

# 2. Cài dependencies
uv sync

# 3. Chạy dev server
uv run uvicorn app.api.main:app --reload --port 8899

# 4. Mở trình duyệt: http://localhost:8899
```

## Tech Stack

- **Backend**: Python 3.12+, FastAPI
- **LLM**: Gemini (qua Beeknoee proxy), LangChain
- **PDF**: PyMuPDF (render trang → ảnh)
- **Frontend**: Reveal.js 6.0.1 (CDN), vanilla HTML/CSS/JS
- **SCORM**: Chuẩn 1.2 (tương thích Moodle, các LMS phổ biến)
