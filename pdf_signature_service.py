"""PDF signature-area detection and X-marker generation for DocQ.

This module is intentionally independent of the DOCX signature detector.
It detects labelled blank areas, nearby handwritten-looking marks, and
interactive PDF signature widgets. Detection is heuristic and results should
be reviewed in the preview before download.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover - optional image-analysis dependency
    cv2 = None
    np = None

try:
    from PIL import Image
    import pytesseract
except Exception:  # pragma: no cover - optional OCR dependency
    Image = None
    pytesseract = None

SIGNATURE_LABEL = re.compile(
    r"\b(?:signature(?:\s+of)?|sign\s+here|signed\s+by|signatory|"
    r"customer\s+signature|client\s+signature|employee\s+signature|"
    r"employer\s+signature|applicant\s+signature|authorized\s+signatory|"
    r"authorised\s+signatory|witness\s+signature|buyer\s+signature|"
    r"seller\s+signature|vendor\s+signature|supplier\s+signature|"
    r"purchaser\s+signature|landlord\s+signature|tenant\s+signature|"
    r"representative\s+signature|approved\s+by)\b",
    re.IGNORECASE,
)


# Match international currency symbols/codes and plain numeric amounts.
# A value is selected only when explicitly associated with an "Amount" label.
_AMOUNT_LABEL = re.compile(r"\bamount\b\s*[:：\-]?\s*", re.IGNORECASE)
_AMOUNT_VALUE = re.compile(
    r"(?P<value>(?:(?:[A-Z]{3}\s*)?[$€£¥₹₩₽₺₫₪₦₱฿₴₡₲₵₸₼₾]\s*|"
    r"[A-Z]{3}\s+)?"
    r"(?:\d{1,3}(?:[,. ]\d{3})+|\d+)"
    r"(?:[.,]\d{1,2})?"
    r"(?:\s*[A-Z]{3})?)",
    re.IGNORECASE,
)


def _normalise_text(value: str) -> str:
    return " ".join((value or "").split())


def _extract_text_lines(page: fitz.Page) -> list[dict[str, Any]]:
    """Return line-level text with PDF-coordinate bounding boxes and font hints."""
    lines: list[dict[str, Any]] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = _normalise_text(" ".join(s.get("text", "") for s in spans))
            if not text:
                continue
            bbox = fitz.Rect(line.get("bbox", block.get("bbox")))
            fonts = [str(s.get("font", "")) for s in spans]
            flags = [int(s.get("flags", 0)) for s in spans]
            lines.append({
                "text": text,
                "bbox": bbox,
                "fonts": fonts,
                "italic": any((f & 1) != 0 for f in flags) or any("italic" in f.lower() or "oblique" in f.lower() for f in fonts),
                "source": "text",
            })
    return lines


def _ocr_lines(page: fitz.Page) -> list[dict[str, Any]]:
    """OCR scanned pages if Tesseract is installed; coordinates are scaled to PDF points."""
    if not pytesseract or not Image:
        return []
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    grouped: dict[tuple[int, int, int], list[int]] = {}
    for i, word in enumerate(data.get("text", [])):
        if not _normalise_text(word):
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        grouped.setdefault(key, []).append(i)
    lines = []
    for indices in grouped.values():
        text = _normalise_text(" ".join(data["text"][i] for i in indices))
        if not text:
            continue
        x0 = min(data["left"][i] for i in indices) / 2
        y0 = min(data["top"][i] for i in indices) / 2
        x1 = max(data["left"][i] + data["width"][i] for i in indices) / 2
        y1 = max(data["top"][i] + data["height"][i] for i in indices) / 2
        lines.append({"text": text, "bbox": fitz.Rect(x0, y0, x1, y1), "fonts": [], "italic": False, "source": "ocr"})
    return lines


def _horizontal_lines_near_label(page: fitz.Page, label_rect: fitz.Rect) -> list[fitz.Rect]:
    candidates: list[fitz.Rect] = []
    search = fitz.Rect(max(0, label_rect.x0 - 20), max(0, label_rect.y0 - 85), min(page.rect.width, label_rect.x1 + 220), label_rect.y1 + 25)
    try:
        for drawing in page.get_drawings():
            for item in drawing.get("items", []):
                if item[0] == "l":
                    p1, p2 = item[1], item[2]
                    if abs(p1.y - p2.y) <= 2 and abs(p2.x - p1.x) >= 35:
                        rect = fitz.Rect(min(p1.x, p2.x), p1.y - 1, max(p1.x, p2.x), p1.y + 1)
                        if search.intersects(rect):
                            candidates.append(rect)
    except Exception:
        pass
    return candidates


def _find_nearby_signature_ink(page: fitz.Page, label_rect: fitz.Rect, lines: list[dict[str, Any]]) -> fitz.Rect | None:
    """Look immediately above a signature label for italic text or non-line ink."""
    # Italic/script-like PDF text is a useful deterministic signal in digitally-created test PDFs.
    nearby = fitz.Rect(
        max(0, label_rect.x0 - 30),
        max(0, label_rect.y0 - 55),
        min(page.rect.width, label_rect.x1 + 140),
        min(page.rect.height, label_rect.y1 + 65),
    )
    italic_boxes = [
        item["bbox"] for item in lines
        if item.get("italic") and nearby.intersects(item["bbox"])
        and not item["bbox"].intersects(label_rect)
    ]
    if italic_boxes:
        result = italic_boxes[0]
        for rect in italic_boxes[1:]:
            result |= rect
        return result

    # For scanned PDFs, render a crop and look for connected non-horizontal ink components.
    if cv2 is None or np is None:
        return None
    crop = fitz.Rect(
        max(0, label_rect.x0 - 20),
        max(0, label_rect.y0 - 50),
        min(page.rect.width, label_rect.x1 + 130),
        min(page.rect.height, label_rect.y1 + 55),
    )
    if crop.width < 15 or crop.height < 8:
        return None
    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=crop, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
    binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)[1]
    # Mask embedded PDF text (e.g. diagonal SAMPLE watermarks and printed labels)
    # before looking for image-based handwriting. OCR-only scanned text is not masked.
    for item in lines:
        if item.get("source") != "text":
            continue
        text_rect = item["bbox"]
        if not crop.intersects(text_rect):
            continue
        clipped = crop & text_rect
        x0 = max(0, int((clipped.x0 - crop.x0) * 3))
        y0 = max(0, int((clipped.y0 - crop.y0) * 3))
        x1 = min(pix.width, int((clipped.x1 - crop.x0) * 3) + 1)
        y1 = min(pix.height, int((clipped.y1 - crop.y0) * 3) + 1)
        if x1 > x0 and y1 > y0:
            binary[y0:y1, x0:x1] = 0
    # Remove long horizontal rules so a signature line is not mistaken for handwriting.
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, pix.width // 5), 1))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
    ink = cv2.subtract(binary, horizontal)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(ink, connectivity=8)
    components = []
    for idx in range(1, count):
        x, y, w, h, area = stats[idx]
        if area >= 5 and h >= 2 and w >= 2 and not (w > pix.width * 0.65 and h < 4):
            components.append((x, y, w, h, area))
    if len(components) < 3:
        return None
    x0 = min(c[0] for c in components) / 3 + crop.x0
    y0 = min(c[1] for c in components) / 3 + crop.y0
    x1 = max(c[0] + c[2] for c in components) / 3 + crop.x0
    y1 = max(c[1] + c[3] for c in components) / 3 + crop.y0
    rect = fitz.Rect(x0, y0, x1, y1)
    if rect.width < 4 or rect.height < 2:
        return None
    return rect


def _signature_widgets(page: fitz.Page) -> list[fitz.Rect]:
    result = []
    try:
        widgets = page.widgets()
        if widgets:
            for widget in widgets:
                field_type = str(getattr(widget, "field_type_string", "")).lower()
                if "signature" in field_type:
                    result.append(fitz.Rect(widget.rect))
    except Exception:
        pass
    return result



def _amount_value_match(text: str, *, after_label: bool) -> tuple[str, int, int] | None:
    """Return the first amount-like value and its character offsets."""
    candidate = text
    if after_label:
        label = _AMOUNT_LABEL.search(candidate)
        if not label:
            return None
        candidate = candidate[label.end():]
        offset = label.end()
    else:
        offset = 0

    leading = len(candidate) - len(candidate.lstrip(" \t:=–—-"))
    candidate = candidate[leading:]
    offset += leading
    match = _AMOUNT_VALUE.match(candidate)
    if not match:
        return None

    value = match.group("value").strip()
    if not value or not re.search(r"\d", value):
        return None
    return value, offset + match.start("value"), offset + match.end("value")


def _amount_value_rect(
    page: fitz.Page, line: dict[str, Any], value: str, start: int, end: int
) -> fitz.Rect:
    """Find the amount's text rectangle, with an OCR geometry fallback."""
    if line.get("source") == "text":
        candidates = [value]
        numeric = re.search(r"\d[\d., ]*", value)
        if numeric:
            candidates.append(numeric.group(0).strip())
        line_rect = fitz.Rect(line["bbox"])
        for candidate in candidates:
            if candidate:
                matches = page.search_for(candidate)
                if matches:
                    matches.sort(
                        key=lambda rect: abs(rect.y0 - line_rect.y0)
                        + abs(rect.x0 - line_rect.x0)
                    )
                    return fitz.Rect(matches[0])

    # OCR fallback: estimate the amount substring's horizontal extent.
    line_text = line.get("text", "")
    line_rect = fitz.Rect(line["bbox"])
    if not line_text or end <= start:
        return line_rect
    left_ratio = max(0.0, min(1.0, start / len(line_text)))
    right_ratio = max(left_ratio, min(1.0, end / len(line_text)))
    x0 = line_rect.x0 + line_rect.width * left_ratio
    x1 = line_rect.x0 + line_rect.width * right_ratio
    return fitz.Rect(x0, line_rect.y0, max(x0 + 2, x1), line_rect.y1)


def _detect_amount_values(
    page: fitz.Page, lines: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Detect only values explicitly associated with an 'Amount' label."""
    found: list[dict[str, Any]] = []

    for label_line in lines:
        label_text = label_line.get("text", "")
        if not _AMOUNT_LABEL.search(label_text):
            continue

        selected = None
        same_line = _amount_value_match(label_text, after_label=True)
        if same_line:
            selected = (label_line, same_line)
        else:
            label_rect = fitz.Rect(label_line["bbox"])
            nearby = []
            for candidate_line in lines:
                if candidate_line is label_line:
                    continue
                candidate_rect = fitz.Rect(candidate_line["bbox"])
                same_row = (
                    abs(candidate_rect.y0 - label_rect.y0)
                    <= max(8, label_rect.height * 0.75)
                    and candidate_rect.x0 >= label_rect.x0
                    and candidate_rect.x0 - label_rect.x1 <= 220
                )
                next_row = (
                    candidate_rect.y0 >= label_rect.y1 - 1
                    and candidate_rect.y0 - label_rect.y1 <= 24
                    and candidate_rect.x0 <= label_rect.x1 + 220
                )
                if not (same_row or next_row):
                    continue
                parsed = _amount_value_match(
                    candidate_line.get("text", ""), after_label=False
                )
                if parsed:
                    distance = (
                        abs(candidate_rect.y0 - label_rect.y0) * 2
                        + abs(candidate_rect.x0 - label_rect.x1)
                    )
                    nearby.append((distance, candidate_line, parsed))

            if nearby:
                _, value_line, parsed = min(nearby, key=lambda item: item[0])
                selected = (value_line, parsed)

        if selected:
            value_line, (value, start, end) = selected
            rect = _amount_value_rect(page, value_line, value, start, end)
            if any(
                item["page"] == page.number + 1
                and fitz.Rect(item["bbox"]).intersects(rect)
                for item in found
            ):
                continue
            found.append({
                "page": page.number + 1,
                "kind": "amount_value",
                "label": "Amount",
                "value": value,
                "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                "confidence": 0.95 if value_line.get("source") == "text" else 0.72,
                "source": value_line.get("source", "text"),
            })

    return found


def detect_pdf_signature_areas(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Detect signature fields and labelled signature areas in a PDF."""
    detections: list[dict[str, Any]] = []
    doc = fitz.open(str(pdf_path))
    try:
        if doc.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported yet.")
        for page_index, page in enumerate(doc):
            lines = _extract_text_lines(page)
            # OCR only when the page has little/no embedded text.
            if sum(len(item["text"]) for item in lines) < 20:
                lines.extend(_ocr_lines(page))

            # Amount highlighting is independent of signature X-marker detection.
            detections.extend(_detect_amount_values(page, lines))

            for widget_rect in _signature_widgets(page):
                detections.append({"page": page_index + 1, "kind": "blank_signature_field", "label": "PDF digital signature field", "bbox": [widget_rect.x0, widget_rect.y0, widget_rect.x1, widget_rect.y1], "placement": [widget_rect.x0 + 3, widget_rect.y1 - 4], "confidence": 0.99})

            for line in lines:
                match = SIGNATURE_LABEL.search(line["text"])
                if not match:
                    continue
                normalized_line = line["text"].strip().lower()
                # Ignore headings and explanatory sentences that mention signatures.
                if (
                    re.search(r"\bsignature\s+(?:area\s+)?(?:detection|marker|analysis|test|recognition)\b", normalized_line)
                    or normalized_line.startswith("page ")
                    or "placeholder" in normalized_line
                    or "fictional names" in normalized_line
                    or "synthetic test marks" in normalized_line
                ):
                    continue
                if match.group(0).strip().lower() == "signature" and normalized_line != "signature":
                    # Ignore prose such as "One signature is present"; a generic
                    # target must be a standalone label to avoid false positives.
                    continue
                label_rect: fitz.Rect = line["bbox"]
                # A lone word "Signature" below an explicit party label is a caption,
                # not a second signature target.
                if normalized_line == "signature":
                    has_parent_label = any(
                        other is not line
                        and other["bbox"].y0 >= label_rect.y0 - 55
                        and other["bbox"].y0 <= label_rect.y0 + 5
                        and re.search(r"\b(?:customer|client|employee|employer|applicant|witness|buyer|seller|vendor|supplier|purchaser|landlord|tenant|authorized|authorised)\b", other["text"], re.I)
                        for other in lines
                    )
                    if has_parent_label:
                        continue
                if any(d["page"] == page_index + 1 and fitz.Rect(d["bbox"]).intersects(label_rect) for d in detections):
                    continue
                ink_rect = _find_nearby_signature_ink(page, label_rect, lines)
                if ink_rect:
                    # Put X beside the detected signature, never over its strokes.
                    x = max(3, ink_rect.x0 - 13)
                    y = min(page.rect.height - 3, max(12, ink_rect.y1 - 2))
                    kind = "existing_handwritten_signature"
                    confidence = 0.78 if line["source"] == "ocr" else 0.88
                    bbox = ink_rect
                else:
                    rules = _horizontal_lines_near_label(page, label_rect)
                    if rules:
                        # Choose the closest rule above the label; mark near its left edge.
                        rule = min(rules, key=lambda r: abs(label_rect.y0 - r.y0))
                        x = max(3, rule.x0 + 3)
                        y = min(page.rect.height - 3, rule.y0 - 3)
                        target = rule | label_rect
                    else:
                        # No visible box/rule: place an X just to the left of the label.
                        x = max(3, label_rect.x0 - 14)
                        y = min(page.rect.height - 3, max(12, label_rect.y0 + 2))
                        target = label_rect
                    kind = "blank_signature_area"
                    confidence = 0.84 if line["source"] == "text" else 0.70
                    bbox = target
                detections.append({"page": page_index + 1, "kind": kind, "label": match.group(0), "bbox": [bbox.x0, bbox.y0, bbox.x1, bbox.y1], "placement": [float(x), float(y)], "confidence": confidence, "source": line["source"]})
    finally:
        doc.close()
    return detections


def create_marked_pdf(original_path: str | Path, output_path: str | Path, detections: list[dict[str, Any]]) -> None:
    """Write X markers onto a copy; never modify the original file."""
    source = fitz.open(str(original_path))
    try:
        if source.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported yet.")
        for detection in detections:
            page_no = int(detection["page"]) - 1
            if page_no < 0 or page_no >= len(source):
                continue
            page = source[page_no]

            if detection.get("kind") == "amount_value":
                rect = fitz.Rect(detection["bbox"])
                highlight = page.add_rect_annot(rect + (-1, -1, 1, 1))
                highlight.set_colors(stroke=None, fill=(1, 1, 0))
                highlight.set_opacity(0.28)
                highlight.update()
                continue

            x, y = detection["placement"]
            page.insert_text((float(x), float(y)), "X", fontname="hebo", fontsize=15, color=(0, 0, 0), overlay=True)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        source.save(str(output_path), garbage=4, deflate=True)
    finally:
        source.close()
