"""Tests cho step3_scorm — slugify + manifest + packing (không cần LLM/PDF)."""

import zipfile

from app.pipeline.step3_scorm import (
    build_manifest_xml,
    pack_scorm,
    slugify_ascii,
)


def test_slugify_ascii_basic():
    assert slugify_ascii("Bài giảng 01") == "Bai_giang_01"
    assert slugify_ascii("Toán & Hóa") == "Toan_Hoa"
    assert slugify_ascii("Trần Xuân Đức") == "Tran_Xuan_uc"


def test_slugify_ascii_empty():
    assert slugify_ascii("///") == "presentation"


def test_build_manifest_contains_required_fields():
    xml = build_manifest_xml("slide2reveal_test", "Tiêu đề & <bài>")
    assert 'identifier="slide2reveal_test"' in xml
    assert 'schema>ADL SCORM</schema' in xml
    assert "schemaversion>1.2" in xml
    assert 'scormtype="sco"' in xml
    assert 'href="index.html"' in xml
    assert 'href="scorm_api.js"' in xml
    # Title phải được escape XML
    assert "Tiêu đề &amp; &lt;bài&gt;" in xml


def test_pack_scorm_zip_contents(tmp_path):
    html = "<html><body><h1>Slide</h1></body></html>"
    out = tmp_path / "bai.zip"
    result = pack_scorm("Bài Giảng", html, out)

    assert result == out
    assert out.exists()

    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
    assert "index.html" in names
    assert "scorm_api.js" in names
    assert "imsmanifest.xml" in names

    # index.html phải chứa SCORM tracking + nội dung gốc
    with zipfile.ZipFile(out) as zf:
        index = zf.read("index.html").decode("utf-8")
    assert "scorm_api.js" in index
    assert "ScormAPI.initialize" in index
    assert "cmi.core.lesson_status" in index
    assert "<h1>Slide</h1>" in index


def test_pack_scorm_assets_in_audio_folder(tmp_path):
    """Audio phải nằm trong thư mục 'audio/' (không rải ở gốc) để khớp manifest 'audio/<hash>.wav'."""
    html = "<html><body></body></html>"
    assets = tmp_path / "audio"
    assets.mkdir()
    (assets / "abc123.wav").write_bytes(b"RIFF....")
    out = tmp_path / "bai.zip"
    pack_scorm("Bài Giảng", html, out, assets_dir=assets)

    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
    assert "audio/abc123.wav" in names
    assert "abc123.wav" not in names  # không rải ở gốc
