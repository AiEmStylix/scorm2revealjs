"""FastAPI web application — Upload PDF → Preview Reveal.js → Download SCORM."""

import logging
import uuid
from pathlib import Path

import jinja2
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings

logger = logging.getLogger(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(title="slide2reveal", description="PDF → Reveal.js → SCORM")

# Static files
_APP_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=_APP_DIR / "static"), name="static")

# Jinja2 Environment — manual setup to avoid Python 3.14 Starlette/Jinja2 cache bug.
# (Starlette's Jinja2Templates injects url_for as a dict-valued global, which creates
# unhashable tuple keys in the template cache on Python 3.14.)
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_APP_DIR / "templates")),
    autoescape=True,
    auto_reload=True,
)


def _render(template_name: str, **context) -> HTMLResponse:
    """Render a Jinja2 template, bypassing Starlette's Jinja2Templates."""
    tmpl = _jinja_env.get_template(template_name)
    html = tmpl.render(**context)
    return HTMLResponse(content=html)


# In-memory job tracking (đủ cho tool nội bộ, không cần DB)
_jobs: dict[str, dict] = {}


def _job_dir(job_id: str) -> Path:
    return settings.jobs_dir / job_id


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Trang chủ — upload PDF."""
    return _render("index.html")


@app.post("/convert")
async def convert(request: Request, file: UploadFile = File(...), title: str = Form("")):
    """Nhận PDF, chạy pipeline, trả job info."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ nhận file PDF.")

    job_id = uuid.uuid4().hex[:12]
    work_dir = _job_dir(job_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Lưu PDF
    pdf_path = work_dir / file.filename
    with open(pdf_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Tiêu đề: từ form hoặc từ tên file
    resolved_title = title.strip() or Path(file.filename).stem

    try:
        # === PIPELINE ===
        from app.pipeline.step0_extract import extract_pdf
        from app.pipeline.step1_transform import transform_to_revealjs
        from app.pipeline.step2_revealjs import build_revealjs_html
        from app.pipeline.step3_scorm import pack_scorm

        # Step 0: Extract PDF → markdown
        logger.info("[Job %s] Step 0: Extracting PDF...", job_id)
        markdown = extract_pdf(pdf_path)
        (work_dir / "extracted.md").write_text(markdown, encoding="utf-8")

        # Step 1: Transform → Reveal.js sections
        logger.info("[Job %s] Step 1: Transforming to Reveal.js...", job_id)
        sections_html = transform_to_revealjs(markdown)
        (work_dir / "sections.html").write_text(sections_html, encoding="utf-8")

        # Step 2: Assemble full Reveal.js
        logger.info("[Job %s] Step 2: Building Reveal.js HTML...", job_id)
        full_html = build_revealjs_html(resolved_title, sections_html)
        revealjs_path = work_dir / "presentation.html"
        revealjs_path.write_text(full_html, encoding="utf-8")

        # Step 3: SCORM packaging
        logger.info("[Job %s] Step 3: Packing SCORM...", job_id)
        scorm_path = work_dir / f"{resolved_title}_scorm.zip"
        pack_scorm(resolved_title, full_html, scorm_path)

        _jobs[job_id] = {
            "title": resolved_title,
            "status": "done",
            "revealjs_path": str(revealjs_path),
            "scorm_path": str(scorm_path),
        }

        logger.info("[Job %s] ✅ Pipeline complete!", job_id)

        # Trả trang kết quả
        return _render("result.html", job_id=job_id, title=resolved_title)

    except Exception as e:
        logger.exception("[Job %s] Pipeline failed: %s", job_id, e)
        _jobs[job_id] = {"title": resolved_title, "status": "error", "error": str(e)}
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")


@app.get("/preview/{job_id}", response_class=HTMLResponse)
async def preview(job_id: str):
    """Xem Reveal.js preview."""
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(status_code=404, detail="Job not found or not complete.")

    revealjs_path = Path(job["revealjs_path"])
    if not revealjs_path.exists():
        raise HTTPException(status_code=404, detail="Presentation file not found.")

    return HTMLResponse(content=revealjs_path.read_text(encoding="utf-8"))


@app.get("/download/{job_id}")
async def download(job_id: str):
    """Download SCORM .zip."""
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(status_code=404, detail="Job not found or not complete.")

    scorm_path = Path(job["scorm_path"])
    if not scorm_path.exists():
        raise HTTPException(status_code=404, detail="SCORM file not found.")

    return FileResponse(
        scorm_path,
        media_type="application/zip",
        filename=scorm_path.name,
    )
