"""Atomic checks for the hand-written exiftool file-metadata adapter.

PURE: no network, no subprocess, no registry side effects. We build a realistic
`exiftool -json` sample (a JSON array of per-file objects, per
https://exiftool.org/exiftool_pod.html) and exercise the pure mapping method plus
the extension gate helper.
"""
from __future__ import annotations

import json

from recontool.adapters.file_metadata import FileMetadata, _has_doc_image_ext

# Realistic `exiftool -json -a report.pdf` output: a JSON ARRAY with one object,
# tag names exactly as exiftool emits them.
_SAMPLE = json.dumps(
    [
        {
            "SourceFile": "report.pdf",
            "FileType": "PDF",
            "MIMEType": "application/pdf",
            "Author": "jdoe",
            "Creator": "Microsoft Word",
            "Producer": "Acrobat Distiller 11.0",
            "Software": "Microsoft Office Word",
            "Company": "Acme Corp",
            "Title": "Q3 Internal Roadmap",
            "GPSLatitude": "37.7749 N",
            "GPSLongitude": "122.4194 W",
            "GPSPosition": "37.7749 N, 122.4194 W",
        }
    ]
)


def test_metadata_exposure_finding_surfaces_author_and_software():
    events = FileMetadata()._events_from_exiftool(
        _SAMPLE, "https://example.com/report.pdf"
    )
    assert len(events) == 1
    ev = events[0]
    assert ev.entity == "finding"
    assert ev.tool == "exiftool"
    assert ev.data["kind"] == "metadata_exposure"
    assert ev.data["asset_value"] == "https://example.com/report.pdf"

    meta = ev.data["metadata"]
    assert meta["Author"] == "jdoe"
    assert meta["Software"] == "Microsoft Office Word"
    assert meta["Company"] == "Acme Corp"
    # Author + Software should be surfaced in the human-readable title too.
    assert "jdoe" in ev.data["title"]


def test_gps_is_attached_when_present():
    events = FileMetadata()._events_from_exiftool(
        _SAMPLE, "https://example.com/report.pdf"
    )
    ev = events[0]
    assert ev.data.get("has_gps") is True
    assert ev.data["gps"]["GPSPosition"] == "37.7749 N, 122.4194 W"


def test_no_finding_when_no_interesting_tags():
    boring = json.dumps([{"SourceFile": "x.png", "FileType": "PNG", "ImageWidth": 10}])
    assert FileMetadata()._events_from_exiftool(boring, "https://example.com/x.png") == []


def test_bare_object_and_garbage_are_tolerated():
    # A bare object (not wrapped in a list) is still handled defensively.
    bare = json.dumps({"Author": "root", "FileType": "JPEG"})
    out = FileMetadata()._events_from_exiftool(bare, "https://example.com/p.jpg")
    assert len(out) == 1
    assert out[0].data["metadata"]["Author"] == "root"
    # Non-JSON never raises.
    assert FileMetadata()._events_from_exiftool("not json", "https://x/y.pdf") == []


def test_extension_gate_filters_html_but_keeps_documents():
    assert _has_doc_image_ext("https://example.com/report.pdf") is True
    assert _has_doc_image_ext("https://example.com/photo.JPG") is True  # case-insensitive
    assert _has_doc_image_ext("https://example.com/doc.docx?v=2#frag") is True  # query/frag ok
    # An HTML page must be filtered out — "no exiftool on an HTML page".
    assert _has_doc_image_ext("https://example.com/index.html") is False
    assert _has_doc_image_ext("https://example.com/") is False
    assert _has_doc_image_ext("https://example.com/api/users") is False


def test_adapter_contract_is_narrow_and_opt_in():
    a = FileMetadata()
    assert a.name == "exiftool"
    assert a.is_active is True
    assert a.default_on is False
    # Narrow consume contract: only document/url-bearing assets, not domains.
    assert a.consumes == ("endpoint", "url")
    assert "domain" not in a.consumes
    assert a.produces == ("finding",)
