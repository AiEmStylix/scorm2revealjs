"""BƯỚC 3 — SCORM 1.2 packaging: Reveal.js HTML → .zip cho LMS.

Rút gọn từ spro/app/pipeline/step6_scorm.py:
- Giữ nguyên: imsmanifest.xml chuẩn SCORM 1.2, scorm_api.js wrapper.
- Khác spro: embed nguyên bài Reveal.js (không phải slide-deck ảnh+audio).
- SCORM báo cáo: lesson_status = "completed" khi user xem đến slide cuối + session_time.
"""

import logging
import re
import shutil
import unicodedata
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def slugify_ascii(text: str) -> str:
    """Chuỗi bất kỳ → ASCII-safe cho identifier SCORM."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9_]+", "_", ascii_only).strip("_") or "presentation"


# scorm_api.js — wrapper SCORM 1.2 tối giản (giữ nguyên từ spro, đã test trên LMS)
SCORM_API_JS = r"""
// scorm_api.js — wrapper SCORM 1.2 cho slide2reveal.
var ScormAPI = (function () {
    var api = null;
    var initialized = false;

    function findAPI(win) {
        var attempts = 0;
        while (win.API == null && win.parent != null && win.parent !== win) {
            attempts += 1;
            if (attempts > 500) return null;
            win = win.parent;
        }
        return win.API || null;
    }

    function getAPI() {
        if (api != null) return api;
        api = findAPI(window);
        if (api == null && window.opener != null) {
            api = findAPI(window.opener);
        }
        if (api == null) {
            console.warn("[ScormAPI] Không tìm thấy API SCORM 1.2 — " +
                "có thể đang mở ngoài LMS.");
        }
        return api;
    }

    function initialize() {
        var a = getAPI();
        if (!a) return false;
        var ok = a.LMSInitialize("") === "true";
        initialized = ok;
        return ok;
    }

    function setValue(key, value) {
        var a = getAPI();
        if (!a || !initialized) return false;
        return a.LMSSetValue(key, String(value)) === "true";
    }

    function getValue(key) {
        var a = getAPI();
        if (!a || !initialized) return "";
        return a.LMSGetValue(key);
    }

    function commit() {
        var a = getAPI();
        if (!a || !initialized) return false;
        return a.LMSCommit("") === "true";
    }

    function finish() {
        var a = getAPI();
        if (!a || !initialized) return false;
        setValue("cmi.core.exit", "");
        commit();
        var ok = a.LMSFinish("") === "true";
        initialized = false;
        return ok;
    }

    return {
        initialize: initialize,
        setValue: setValue,
        getValue: getValue,
        commit: commit,
        finish: finish,
    };
})();

function scormFormatSessionTime(totalSeconds) {
    var h = Math.floor(totalSeconds / 3600);
    var m = Math.floor((totalSeconds % 3600) / 60);
    var s = Math.floor(totalSeconds % 60);
    function pad(n) { return (n < 10 ? "0" : "") + n; }
    return pad(h) + ":" + pad(m) + ":" + pad(s);
}
""".strip()


def _build_scorm_index_html(title: str, revealjs_html: str) -> str:
    """Wrap Reveal.js HTML với SCORM tracking code.

    Thêm JS đoạn cuối: initialize SCORM, lắng nghe slidechanged event của Reveal.js,
    khi đến slide cuối → báo "completed".
    """
    # Chèn SCORM script ngay trước </body>
    scorm_tracking_js = """
<script src="scorm_api.js"></script>
<script>
(function() {
    var sessionStartMs = Date.now();
    var completed = false;

    // Chờ Reveal.js ready
    if (typeof Reveal !== 'undefined') {
        Reveal.on('ready', function() {
            ScormAPI.initialize();
        });

        Reveal.on('slidechanged', function(event) {
            // Kiểm tra nếu đã đến slide cuối
            var totalSlides = Reveal.getTotalSlides();
            var currentSlide = Reveal.getSlidePastCount() + 1;

            if (currentSlide >= totalSlides && !completed) {
                completed = true;
                ScormAPI.setValue("cmi.core.lesson_status", "completed");
                var elapsed = Math.round((Date.now() - sessionStartMs) / 1000);
                ScormAPI.setValue("cmi.core.session_time", scormFormatSessionTime(elapsed));
                ScormAPI.commit();
            }
        });
    }

    window.addEventListener("beforeunload", function() {
        if (!completed) {
            ScormAPI.setValue("cmi.core.lesson_status", "incomplete");
            var elapsed = Math.round((Date.now() - sessionStartMs) / 1000);
            ScormAPI.setValue("cmi.core.session_time", scormFormatSessionTime(elapsed));
            ScormAPI.commit();
        }
        ScormAPI.finish();
    });
})();
</script>"""

    # Chèn trước </body>
    return revealjs_html.replace("</body>", scorm_tracking_js + "\n</body>")


def build_manifest_xml(identifier: str, title: str) -> str:
    """imsmanifest.xml chuẩn SCORM 1.2 (giữ nguyên từ spro, đã test trên LMS)."""
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<manifest identifier="{identifier}"
          xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                               http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="{identifier}_org">
    <organization identifier="{identifier}_org">
      <title>{safe_title}</title>
      <item identifier="item_1" identifierref="resource_1">
        <title>{safe_title}</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="resource_1" type="webcontent" adlcp:scormtype="sco" href="index.html">
      <file href="index.html"/>
      <file href="scorm_api.js"/>
    </resource>
  </resources>
</manifest>
"""


def pack_scorm(title: str, revealjs_html: str, output_path: Path, *, assets_dir: Path | None = None) -> Path:
    """Đóng gói SCORM 1.2: Reveal.js HTML + manifest + scorm_api.js → .zip.

    Args:
        title: tiêu đề bài giảng (dùng cho manifest).
        revealjs_html: full Reveal.js HTML từ step2.
        output_path: đường dẫn file .zip đầu ra.
        assets_dir: thư mục asset cần đóng gói kèm (vd thư mục audio/ của TTS) — giữ nguyên
            cấu trúc tương đối để đường dẫn tương đối trong HTML chạy được trong .zip.

    Returns:
        Path tới file .zip đã tạo.
    """
    identifier = f"slide2reveal_{slugify_ascii(title)}"
    build_dir = output_path.parent / "_scorm_build"

    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    # Ghi files
    index_html = _build_scorm_index_html(title, revealjs_html)
    (build_dir / "index.html").write_text(index_html, encoding="utf-8")
    (build_dir / "scorm_api.js").write_text(SCORM_API_JS, encoding="utf-8")
    (build_dir / "imsmanifest.xml").write_text(
        build_manifest_xml(identifier, title), encoding="utf-8"
    )

    # Copy assets (audio TTS) GIỮ NGUYÊN thư mục gốc. Ví dụ assets_dir=".../audio" có
    # "<hash>.wav" → build/audio/<hash>.wav — khớp đường dẫn tương đối "audio/<hash>.wav"
    # trong HTML/manifest (khi mở SCORM offline).
    if assets_dir and assets_dir.exists():
        for file_path in assets_dir.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(assets_dir)
                dest = build_dir / assets_dir.name / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest)

    # Nén zip
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in build_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(build_dir))

    shutil.rmtree(build_dir)
    logger.info("[SCORM] OK → %s", output_path.name)
    return output_path
