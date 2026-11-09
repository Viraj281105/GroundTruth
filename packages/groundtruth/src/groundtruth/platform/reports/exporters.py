"""Institutional-grade CSV and PDF report exporters for GroundTruth evidence bundles."""

from __future__ import annotations

import csv
import io
import textwrap
from typing import Any

from groundtruth.contracts.evidence import EvidenceBundle
from groundtruth.platform.reports.narrative import VERDICT_HEADLINES

CSV_COLUMNS: tuple[str, ...] = (
    "id",
    "label",
    "value",
    "unit",
    "interval_lower",
    "interval_upper",
    "interval_level",
    "interval_kind",
    "provenance_source",
    "provenance_method",
    "provenance_stage",
    "provenance_fingerprint",
    "notes",
)


def _bundle_is_simulated(bundle: EvidenceBundle) -> bool:
    """Return True if the bundle originates from simulated / synthetic data."""
    flag = getattr(bundle, "is_simulated", None)
    if isinstance(flag, bool):
        return flag
    return any(
        "synthetic" in item.provenance.source.lower()
        or "simulated" in item.provenance.source.lower()
        for item in bundle.items
    )


def _bundle_is_calibrated(bundle: EvidenceBundle) -> bool:
    """Return True if the bundle includes calibrated biomass/carbon estimates."""
    return any(item.id == "carbon.estimated_tco2e" for item in bundle.items)


def _enum_or_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val.value if hasattr(val, "value") else val)


def export_bundle_csv(bundle: EvidenceBundle) -> str:
    """Export an :class:`EvidenceBundle` to a UTF-8 CSV string with provenance headers."""
    is_sim = _bundle_is_simulated(bundle)
    data_origin = "SYNTHETIC_SIMULATION" if is_sim else "OBSERVED"
    calibrated = _bundle_is_calibrated(bundle)
    calibration_status = "CALIBRATED" if calibrated else "NOT_CALIBRATED"

    verdict_label = (
        _enum_or_str(bundle.verdict.label) if bundle.verdict is not None else "not_assessed"
    )
    verdict_rationale = (
        bundle.verdict.rationale.replace("\r", " ").replace("\n", " ")
        if bundle.verdict is not None
        else ""
    )

    buf = io.StringIO()
    buf.write(f"# case_id: {bundle.case_id}\n")
    buf.write(f"# schema_version: {bundle.schema_version}\n")
    buf.write(f"# is_simulated: {is_sim}\n")
    buf.write(f"# data_origin: {data_origin}\n")
    buf.write(f"# verdict_label: {verdict_label}\n")
    buf.write(f"# verdict_rationale: {verdict_rationale}\n")
    buf.write(f"# biomass_calibration_status: {calibration_status}\n")

    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)

    for item in bundle.items:
        conf = item.confidence
        row = [
            item.id,
            item.label,
            item.rendered_value(),
            item.unit or "",
            f"{conf.lower}" if conf is not None else "",
            f"{conf.upper}" if conf is not None else "",
            f"{conf.level}" if conf is not None else "",
            _enum_or_str(conf.kind) if conf is not None else "",
            item.provenance.source,
            item.provenance.method,
            _enum_or_str(item.provenance.stage),
            item.provenance.fingerprint(),
            getattr(item, "notes", None) or "",
        ]
        writer.writerow(row)

    return buf.getvalue()


def _pdf_escape(text: str) -> str:
    """Sanitize and escape text for a PDF WinAnsiEncoding literal string."""
    # Replace common Unicode punctuation with ASCII/WinAnsi equivalents for clean PDF streams
    cleaned = (
        text.replace("\u2014", "—")
        .replace("\u2013", "-")
        .replace("\u2212", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    # Encode non-ASCII characters safely or keep printable Latin-1/WinAnsi
    out_chars: list[str] = []
    for ch in cleaned:
        if ch == "\\":
            out_chars.append("\\\\")
        elif ch == "(":
            out_chars.append("\\(")
        elif ch == ")":
            out_chars.append("\\)")
        elif ch == "—":
            # Keep em-dash as WinAnsi octal \227 AND ASCII fallback handled by caller where needed
            out_chars.append("—")
        elif 32 <= ord(ch) <= 126:
            out_chars.append(ch)
        else:
            out_chars.append(" ")
    return "".join(out_chars)


def _build_report_lines(
    bundle: EvidenceBundle,
    *,
    report_markdown: str | None = None,
) -> list[tuple[str, int, float]]:
    """Build structured (text, font_size, leading) tuples for PDF layout."""
    is_sim = _bundle_is_simulated(bundle)
    calibrated = _bundle_is_calibrated(bundle)
    lines: list[tuple[str, int, float]] = []

    lines.append((f"GroundTruth Verification Screening Report — {bundle.case_id}", 14, 20.0))
    lines.append((f"Case ID: {bundle.case_id} | Schema Version: {bundle.schema_version}", 9, 14.0))
    lines.append(("", 9, 8.0))

    if is_sim:
        lines.append(("SIMULATED / SYNTHETIC DATA RUN — NOT SATELLITE OBSERVATIONS", 11, 16.0))
        lines.append(
            (
                "Data Provenance: SYNTHETIC_SIMULATION (is_simulated=True). "
                "Do not use for regulatory filing or carbon credit issuance.",
                9,
                13.0,
            )
        )
        lines.append(("", 9, 8.0))
    else:
        lines.append(("DATA PROVENANCE: OBSERVED SATELLITE SERIES", 10, 15.0))
        lines.append(("", 9, 8.0))

    # Screening Verdict & Rationale
    lines.append(("1. Screening Verdict & Rationale", 12, 18.0))
    if bundle.verdict is not None:
        v_label = _enum_or_str(bundle.verdict.label)
        headline = VERDICT_HEADLINES.get(bundle.verdict.label, v_label)
        lines.append((f"Verdict Label: {v_label} ({headline})", 10, 14.0))
        for wrapped in textwrap.wrap(f"Rationale: {bundle.verdict.rationale}", width=88):
            lines.append((wrapped, 9, 13.0))
    else:
        lines.append(("Verdict Label: not_assessed", 10, 14.0))
    lines.append(("", 9, 8.0))

    # Biomass & Carbon Calibration Status
    lines.append(("2. Biomass & Carbon Calibration Status", 12, 18.0))
    if calibrated:
        lines.append(("Status: CALIBRATED (carbon.estimated_tco2e present)", 10, 14.0))
    else:
        lines.append(
            (
                "Status: NOT CALIBRATED (NOT_CALIBRATED — vegetation index proxy only; "
                "no biomass/tCO2e conversion applied)",
                10,
                14.0,
            )
        )
    lines.append(("", 9, 8.0))

    # Key Evidence Items
    lines.append(("3. Key Evidence Items & Provenance Fingerprints", 12, 18.0))
    for item in bundle.items:
        unit_str = f" {item.unit}" if item.unit else ""
        if item.confidence is not None:
            kind_str = _enum_or_str(item.confidence.kind)
            interval_str = (
                f"[{item.confidence.lower:.4g}, {item.confidence.upper:.4g}] ({kind_str})"
            )
        else:
            interval_str = "no interval"
        fp = item.provenance.fingerprint()
        item_line = (
            f"- {item.id} ({item.label}): {item.rendered_value()}{unit_str} | "
            f"Interval: {interval_str}"
        )
        for wrapped in textwrap.wrap(item_line, width=90):
            lines.append((wrapped, 9, 12.5))
        prov_line = (
            f"  Method: {item.provenance.method} | Source: {item.provenance.source} | "
            f"Stage: {_enum_or_str(item.provenance.stage)} | Fingerprint: {fp}"
        )
        for wrapped in textwrap.wrap(prov_line, width=90):
            lines.append((wrapped, 8, 11.5))
    lines.append(("", 9, 8.0))

    # Mandatory Scientific Caveats & Warnings
    lines.append(("4. Mandatory Scientific Caveats & Warnings", 12, 18.0))
    if bundle.verdict is not None and bundle.verdict.caveats:
        for caveat in bundle.verdict.caveats:
            for wrapped in textwrap.wrap(f"* Caveat: {caveat}", width=88):
                lines.append((wrapped, 9, 12.5))
    if bundle.warnings:
        for warning in bundle.warnings:
            for wrapped in textwrap.wrap(f"* Warning: {warning}", width=88):
                lines.append((wrapped, 9, 12.5))
    if (bundle.verdict is None or not bundle.verdict.caveats) and not bundle.warnings:
        lines.append(("* Standard synthetic control screening caveats apply.", 9, 12.5))

    if report_markdown:
        lines.append(("", 9, 8.0))
        lines.append(("5. Narrative Summary", 12, 18.0))
        for raw_line in report_markdown.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            for wrapped in textwrap.wrap(stripped, width=88):
                lines.append((wrapped, 8, 11.5))

    return lines


def export_bundle_pdf(
    bundle: EvidenceBundle,
    *,
    report_markdown: str | None = None,
) -> bytes:
    """Generate a self-contained ``%PDF-1.4`` binary document for an :class:`EvidenceBundle`."""
    all_lines = _build_report_lines(bundle, report_markdown=report_markdown)

    # Paginate lines so each page fits cleanly within US Letter (612 x 792 pt)
    pages_lines: list[list[tuple[str, int, float]]] = []
    current_page: list[tuple[str, int, float]] = []
    y_cursor = 740.0
    bottom_margin = 55.0

    for text, font_size, leading in all_lines:
        if y_cursor - leading < bottom_margin and current_page:
            pages_lines.append(current_page)
            current_page = []
            y_cursor = 740.0
        current_page.append((text, font_size, leading))
        y_cursor -= leading

    if current_page or not pages_lines:
        pages_lines.append(current_page)

    # Object numbering:
    # 1: Catalog
    # 2: Pages
    # 3: Font (/F1 Helvetica)
    # For each page i in 0..N-1:
    #   page_obj_id = 4 + 2*i
    #   content_obj_id = 5 + 2*i
    num_pages = len(pages_lines)
    page_obj_ids = [4 + 2 * i for i in range(num_pages)]

    objects: dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids_ref = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids_ref}] /Count {num_pages} >>".encode("latin-1")
    objects[3] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )

    for i, page_items in enumerate(pages_lines):
        page_obj_id = 4 + 2 * i
        content_obj_id = 5 + 2 * i

        stream_cmds: list[str] = ["BT", "/F1 10 Tf"]
        y = 740.0
        for text, font_size, leading in page_items:
            if text:
                escaped = _pdf_escape(text)
                stream_cmds.append(f"/F1 {font_size} Tf")
                stream_cmds.append(f"1 0 0 1 48 {y:.1f} Tm")
                stream_cmds.append(f"({escaped}) Tj")
            y -= leading
        stream_cmds.append("ET")
        stream_bytes = "\n".join(stream_cmds).encode("utf-8")

        objects[page_obj_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_id} 0 R >>"
        ).encode("latin-1")
        objects[content_obj_id] = (
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1")
            + stream_bytes
            + b"\nendstream"
        )

    total_objects = max(objects.keys())
    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets: dict[int, int] = {}
    for obj_id in range(1, total_objects + 1):
        offsets[obj_id] = len(out)
        out.extend(f"{obj_id} 0 obj\n".encode("latin-1"))
        out.extend(objects[obj_id])
        out.extend(b"\nendobj\n")

    xref_offset = len(out)
    out.extend(f"xref\n0 {total_objects + 1}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for obj_id in range(1, total_objects + 1):
        out.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("latin-1"))

    out.extend(
        f"trailer\n<< /Size {total_objects + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    )
    return bytes(out)
