from pathlib import Path
import json
import uuid
import shutil
import fitz

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.pdf_document_service import extract_digital_pdf_text
from app.gemini_service import analyze_document

router = APIRouter(prefix="/api/v1/pdf-documents", tags=["PDF Documents"])

BASE_DIR = Path("storage/pdf-documents")
UPLOAD_DIR = BASE_DIR / "uploads"
TEXT_DIR = BASE_DIR / "extracted"
ANALYSIS_DIR = BASE_DIR / "analysis"
EDITED_DIR = BASE_DIR / "edited"
GENERATED_DIR = BASE_DIR / "generated"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEXT_DIR.mkdir(parents=True, exist_ok=True)
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
EDITED_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
AQ.Ab8RN6KzThB2aayHPDclBD9TMKN6PIs1Tolyq3E5rhlr3GfY



class EditedField(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    field_type: str = Field(default="string", max_length=100)
    value: str = Field(default="", max_length=10000)


class SaveEditedFieldsRequest(BaseModel):
    fields: list[EditedField] = Field(..., max_length=500)


def _validate_document_id(document_id: str):
    if not document_id or not all(c in "0123456789abcdef" for c in document_id.lower()):
        raise HTTPException(status_code=400, detail="Invalid PDF document ID.")
    text_path = (TEXT_DIR / f"{document_id}.txt").resolve()
    try:
        text_path.relative_to(TEXT_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid PDF document path.")
    if not text_path.exists() or not text_path.is_file():
        raise HTTPException(status_code=404, detail="PDF document not found. Upload it first.")
    return text_path



@router.post("/upload")
async def upload_pdf_document(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    document_id = uuid.uuid4().hex
    safe_filename = Path(file.filename).name
    original_path = UPLOAD_DIR / f"{document_id}_{safe_filename}"

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")
        if not content.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF.")
        original_path.write_bytes(content)

        try:
            extracted = extract_digital_pdf_text(str(original_path))
        except ValueError as exc:
            original_path.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=str(exc))
        except Exception as exc:
            original_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Unable to read PDF: {exc}")

        text_path = TEXT_DIR / f"{document_id}.txt"
        text_path.write_text(extracted["text"], encoding="utf-8")

        return {
            "message": "Digital PDF uploaded and text extracted successfully.",
            "document_id": document_id,
            "filename": safe_filename,
            "page_count": extracted["page_count"],
            "character_count": extracted["character_count"],
            "extracted_text": extracted["text"],
            "analysis_status": "PENDING"
        }
    except HTTPException:
        raise
    except Exception as exc:
        original_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"PDF upload failed: {exc}")


@router.post("/{document_id}/analyze")
def analyze_pdf_document(document_id: str):
    # Validate the ID before using it in a filesystem path.
    if not document_id or not all(c in "0123456789abcdef" for c in document_id.lower()):
        raise HTTPException(status_code=400, detail="Invalid PDF document ID.")

    text_path = (TEXT_DIR / f"{document_id}.txt").resolve()
    text_dir_resolved = TEXT_DIR.resolve()

    try:
        text_path.relative_to(text_dir_resolved)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid PDF document path.")

    if not text_path.exists() or not text_path.is_file():
        raise HTTPException(status_code=404, detail="Extracted PDF text not found. Upload the PDF first.")

    document_text = text_path.read_text(encoding="utf-8")
    if not document_text.strip():
        raise HTTPException(status_code=422, detail="The PDF contains no extractable text.")

    try:
        analysis = analyze_document(document_text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PDF AI analysis failed: {exc}")

    analysis_path = ANALYSIS_DIR / f"{document_id}.json"
    analysis_path.write_text(
        json.dumps(analysis.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return {
        "message": "PDF analyzed successfully.",
        "document_id": document_id,
        "analysis_status": "COMPLETED",
        "analysis": analysis
    }




def _get_original_pdf_path(document_id: str) -> Path:
    _validate_document_id(document_id)
    candidates = list(UPLOAD_DIR.glob(f"{document_id}_*.pdf"))
    if not candidates:
        raise HTTPException(status_code=404, detail="Original PDF file not found.")
    return candidates[0]


def _find_label_rect(page, field_name: str):
    """Prefer an exact label-with-colon match to avoid matching headings or prose."""
    label = field_name.strip().rstrip(":")
    if not label:
        return None

    # Exact punctuation-bearing label is the safest anchor (e.g. "Age:").
    exact_hits = page.search_for(f"{label}:", quads=False)
    if exact_hits:
        return exact_hits[0]

    # Fall back to the bare label only when no colon-form label exists.
    hits = page.search_for(label, quads=False)
    if not hits:
        return None

    # If there are several hits (common for short names such as Age), prefer
    # one whose right side has a nearby horizontal line, rather than a heading.
    drawings = page.get_drawings()
    def line_score(rect):
        x0, y0, x1, y1 = rect
        best = 1e9
        for drawing in drawings:
            for item in drawing.get("items", []):
                if item[0] != "l":
                    continue
                a, b = item[1], item[2]
                if abs(a.y - b.y) > 2.0:
                    continue
                lx0, lx1 = min(a.x, b.x), max(a.x, b.x)
                ly = (a.y + b.y) / 2.0
                if lx0 >= x1 - 1 and y0 - 5 <= ly <= y1 + 12 and lx1 - lx0 >= 30:
                    best = min(best, abs(ly - y1))
        return best
    ranked = sorted(hits, key=line_score)
    # Do not use a short/ambiguous bare-word hit unless it has a nearby line.
    if line_score(ranked[0]) >= 1e8:
        return None
    return ranked[0]


def _collect_blank_targets(page, label_rect):
    """Return a safe target region for a blank field, based on nearby drawn lines/boxes."""
    if label_rect is None:
        return None
    drawings = page.get_drawings()
    candidates = []
    lx0, ly0, lx1, ly1 = label_rect

    # Horizontal lines: same-row line to the right of the label, or a line
    # immediately below the label (for stacked form layouts).
    for drawing in drawings:
        for item in drawing.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) > 2.0:
                    continue
                x0, x1 = min(p1.x, p2.x), max(p1.x, p2.x)
                y = (p1.y + p2.y) / 2.0
                # Same line: starts after label and is close to label baseline.
                if x0 >= lx1 - 1 and ly0 - 8 <= y <= ly1 + 22 and x1 - x0 >= 30:
                    candidates.append((0, abs(y - ly1), fitz.Rect(x0 + 2, y - 17, x1 - 2, y - 3), "same-line"))
                # Horizontal writing line may sit slightly below the label baseline
                # and begin to the right of the label (common in German forms).
                elif y > ly1 + 2 and y <= ly1 + 65 and x0 >= lx1 - 1 and x1 - x0 >= 30:
                    candidates.append((0, y - ly1, fitz.Rect(x0 + 2, y - 17, x1 - 2, y - 3), "same-line"))
                # Stacked layout: writing line begins near the label's left edge.
                elif y > ly1 + 2 and y <= ly1 + 65 and x0 <= lx0 + 12 and x1 - x0 >= 30:
                    candidates.append((1, y - ly1, fitz.Rect(x0 + 2, y - 17, x1 - 2, y - 3), "below-label"))
            elif item[0] == "re":
                rect = fitz.Rect(item[1])
                # Empty box near/under the label.
                if rect.width >= 30 and rect.height >= 10 and rect.height <= 100:
                    if rect.x0 >= lx1 - 1 and ly0 - 5 <= rect.y0 <= ly1 + 65:
                        candidates.append((0, abs(rect.y0 - ly1), fitz.Rect(rect.x0 + 3, rect.y0 + 2, rect.x1 - 3, rect.y1 - 2), "box"))
                    elif rect.y0 > ly1 and rect.y0 <= ly1 + 65 and rect.x0 <= lx0 + 12:
                        candidates.append((1, rect.y0 - ly1, fitz.Rect(rect.x0 + 3, rect.y0 + 2, rect.x1 - 3, rect.y1 - 2), "box-below"))

    candidates.sort(key=lambda c: (c[0], c[1]))
    for _, _, rect, placement in candidates:
        if rect.width > 15 and rect.height > 5:
            return {"rect": rect, "placement": placement}
    return None





def _collect_underscore_target(page, label_rect, field_name):
    """Find a text underscore placeholder associated with a field label."""
    if label_rect is None:
        return None
    label = fitz.Rect(label_rect)
    candidates = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if "_" not in text:
                    continue
                # Only treat long underscore runs as blank placeholders.
                import re
                for match in re.finditer(r"_{4,}", text):
                    bbox = fitz.Rect(span["bbox"])
                    run_text = match.group(0)
                    prefix = text[:match.start()]
                    suffix = text[match.end():]
                    size = float(span.get("size", 11))
                    font = span.get("font", "Helvetica")
                    # For standard fonts, use font metrics to calculate the run's
                    # x-position. For unknown fonts, use proportional span width.
                    try:
                        x0 = bbox.x0 + fitz.get_text_length(prefix, fontname=font, fontsize=size)
                        run_width = fitz.get_text_length(run_text, fontname=font, fontsize=size)
                    except Exception:
                        total_chars = max(1, len(text))
                        x0 = bbox.x0 + bbox.width * (match.start() / total_chars)
                        run_width = bbox.width * (len(run_text) / total_chars)
                    run_rect = fitz.Rect(x0, bbox.y0, x0 + run_width, bbox.y1)
                    # Same row, to the right of the label; or a blank directly
                    # beneath the label. Also allow label and underscores in one span.
                    same_row = (run_rect.x0 >= label.x1 - 1 and
                                label.y0 - 5 <= run_rect.y0 <= label.y1 + 8)
                    below_label = (run_rect.y0 > label.y1 + 2 and
                               run_rect.y0 <= label.y1 + 65 and
                               run_rect.x0 <= label.x0 + 12)
                    combined_span = field_name.lower() in text.lower()
                    if same_row or below_label or combined_span:
                        candidates.append((0 if same_row or combined_span else 1,
                                          abs(run_rect.y0 - label.y0), run_rect))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return {"rect": candidates[0][2], "placement": "underscore"}


def _fill_underscore_target(page, rect, value, max_font=11):
    """Remove underscore text, restore a clean underline, and place value above it."""
    box = fitz.Rect(rect)
    value = str(value or "").strip()
    if not value or box.width < 15 or box.height < 5:
        return False, None
    # Redact only the placeholder characters, leaving the label untouched.
    page.add_redact_annot(box, fill=(1, 1, 1))
    page.apply_redactions()
    line_y = box.y1 - 3.0
    page.draw_line(fitz.Point(box.x0, line_y), fitz.Point(box.x1, line_y),
                   color=(0, 0, 0), width=0.55)
    font_size = max_font
    while font_size >= 6:
        width = fitz.get_text_length(value, fontname="helv", fontsize=font_size)
        if width <= box.width:
            page.insert_text((box.x0, line_y - 2.0), value, fontsize=font_size,
                            fontname="helv", color=(0, 0, 0))
            return True, font_size
        font_size -= 0.5
    return False, None

def _collect_table_cell_target(page, label_rect):
    """Find the smallest drawn rectangle enclosing a label and return the blank area below it."""
    if label_rect is None:
        return None
    label = fitz.Rect(label_rect)
    candidates = []
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if item[0] != "re":
                continue
            cell = fitz.Rect(item[1])
            # Require the label to be inside the rectangle with a small tolerance.
            if (cell.width >= 50 and cell.height >= 24 and
                cell.x0 <= label.x0 + 1 and cell.x1 >= label.x1 - 1 and
                cell.y0 <= label.y0 + 2 and cell.y1 >= label.y1 - 2):
                # Label should be near the top of the cell; otherwise this may be
                # a larger container or an unrelated enclosing border.
                if label.y0 - cell.y0 <= cell.height * 0.45:
                    candidates.append(cell)
    if not candidates:
        return None
    cell = min(candidates, key=lambda r: r.width * r.height)
    # Interior writing region below the label, with consistent padding.
    horizontal_padding = 6.5
    vertical_top_padding = 7.0
    vertical_bottom_padding = 6.5
    target = fitz.Rect(cell.x0 + horizontal_padding, label.y1 + vertical_top_padding, cell.x1 - horizontal_padding, label.y1 + vertical_top_padding)
    target.y1 = cell.y1 - vertical_bottom_padding
    if target.width < 20 or target.height < 8:
        return None
    return {
        "rect": target,
        "placement": "table-cell",
    }

def _insert_text_in_rect(page, rect, value, max_font=12, placement="line"):
    box = fitz.Rect(rect)
    value = str(value or "").strip()

    if not value or box.width <= 0 or box.height <= 0:
        return False, None

    # Boxes: vertically fit the text inside the rectangle.
    if placement in ("box", "table-cell"):
        font_size = min(max_font, box.height * 0.65)

        while font_size >= 6:
            spare = page.insert_textbox(
                box,
                value,
                fontsize=font_size,
                fontname="helv",
                color=(0, 0, 0),
                align=0,
            )
            if spare >= 0:
                return True, font_size
            font_size -= 0.5

        return False, None

    # Horizontal lines: position text using its baseline.
    font_size = max_font

    while font_size >= 6:
        text_width = fitz.get_text_length(
            value,
            fontname="helv",
            fontsize=font_size
        )

        if text_width <= box.width:
            # The bottom of the target rectangle is close to the underline.
            # Insert using a baseline rather than a textbox.
            baseline = box.y1

            page.insert_text(
                (box.x0, baseline),
                value,
                fontsize=font_size,
                fontname="helv",
                color=(0, 0, 0),
            )

            return True, font_size

        font_size -= 0.5

    return False, None

@router.post("/{document_id}/generate")
def generate_edited_pdf(document_id: str):
    """Generate edited PDF: replace existing text and fill detected blank lines/boxes."""
    original_path = _get_original_pdf_path(document_id)
    analysis_path = ANALYSIS_DIR / f"{document_id}.json"
    edited_path = EDITED_DIR / f"{document_id}.json"
    if not analysis_path.exists():
        raise HTTPException(status_code=404, detail="AI analysis not found. Analyze the PDF first.")
    if not edited_path.exists():
        raise HTTPException(status_code=404, detail="Edited fields not found. Save edits first.")
    try:
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        edited = json.loads(edited_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="Saved analysis or edits could not be read.")

    old_fields = analysis.get("fields", [])
    new_fields = edited.get("fields", [])
    old_by_name = {str(f.get("name", "")).strip().casefold(): f for f in old_fields if isinstance(f, dict)}
    changes, blank_fields, unmatched = [], [], []
    for field in new_fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name", "")).strip()
        source = old_by_name.get(name.casefold())
        new_value = str(field.get("value", "") or "").strip()
        if not new_value:
            continue
        old_value = str(source.get("value", "") or "").strip() if source else ""
        if source and old_value and old_value != new_value:
            changes.append({"field": name, "old": old_value, "new": new_value})
        else:
            blank_fields.append({"field": name, "value": new_value})

    generated_path = GENERATED_DIR / f"{document_id}_edited.pdf"
    try:
        doc = fitz.open(original_path)
        # Existing text replacements: locate and redact before insertion.
        replacement_hits = {}
        for change in changes:
            hits = []
            for page_index, page in enumerate(doc):
                hits.extend((page_index, rect) for rect in page.search_for(change["old"]))
            change["hits"] = hits
            if not hits:
                unmatched.append({"field": change["field"], "reason": "Source text not found in PDF."})
            for page_index, rect in hits:
                replacement_hits.setdefault(page_index, []).append((rect, change))
        for page_index, items in replacement_hits.items():
            page = doc[page_index]
            for rect, change in items:
                page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()
            for rect, change in items:
                box = fitz.Rect(rect)
                box.x0 += 0.5; box.x1 -= 0.5; box.y0 += 0.2; box.y1 -= 0.2
                ok, fs = _insert_text_in_rect(page, box, change["new"], max_font=11)
                if ok:
                    change["inserted_count"] = change.get("inserted_count", 0) + 1
                else:
                    unmatched.append({"field": change["field"], "reason": "Replacement text did not fit the source text area."})

        # Blank fields: detect labels and nearby line/box geometry. Avoid guessing
        # when there is no reliable geometric target.
        blank_applied = []
        for item in blank_fields:
            name, value = item["field"], item["value"]
            placements_count = 0
            for page_index, page in enumerate(doc):
                label_rect = _find_label_rect(page, name)
                # Text underscores are checked first because they are not drawing
                # objects and therefore cannot be found by line/rectangle geometry.
                target = _collect_underscore_target(page, label_rect, name)
                if target:
                    ok, fs = _fill_underscore_target(page, target["rect"], value, max_font=11)
                else:
                    # Keep existing table-cell, drawn-line, and box behavior.
                    target = _collect_table_cell_target(page, label_rect)
                    if not target:
                        target = _collect_blank_targets(page, label_rect)
                    if not target:
                        continue
                    ok, fs = _insert_text_in_rect(
                        page, target["rect"], value, max_font=11,
                        placement=target["placement"]
                    )
                if ok:
                    blank_applied.append({"field": name, "value": value, "page": page_index + 1,
                                        "placement": target["placement"], "font_size": fs})
                    placements_count += 1
            if placements_count == 0:
                unmatched.append({"field": name, "reason": "No clear blank line or box found near the label; not placed to avoid guessing."})

        doc.save(generated_path, garbage=4, deflate=True)
        doc.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    applied = [{"field": ch["field"], "old_value": ch["old"], "new_value": ch["new"],
                "matches": len(ch.get("hits", [])), "inserted": ch.get("inserted_count", 0)} for ch in changes]
    return {"message": "Generated PDF created.", "document_id": document_id,
            "generated_filename": generated_path.name,
            "download_url": f"/api/v1/pdf-documents/{document_id}/generated",
            "applied_changes": applied, "blank_fields_filled": blank_applied,
            "unmatched_fields": unmatched}


@router.get("/{document_id}/generated")
def download_generated_pdf(document_id: str):
    _validate_document_id(document_id)
    generated_path = (GENERATED_DIR / f"{document_id}_edited.pdf").resolve()
    try:
        generated_path.relative_to(GENERATED_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid generated PDF path.")
    if not generated_path.exists():
        raise HTTPException(status_code=404, detail="Generated PDF not found. Generate it first.")
    return FileResponse(str(generated_path), media_type="application/pdf", filename=generated_path.name)


@router.put("/{document_id}/edited")
def save_edited_pdf_fields(document_id: str, request: SaveEditedFieldsRequest):
    _validate_document_id(document_id)
    edited_path = (EDITED_DIR / f"{document_id}.json").resolve()
    try:
        edited_path.relative_to(EDITED_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid edited data path.")

    payload = {
        "document_id": document_id,
        "fields": [field.model_dump() for field in request.fields],
    }
    edited_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "message": "Edited PDF fields saved successfully.",
        "document_id": document_id,
        "field_count": len(request.fields),
        "fields": payload["fields"],
    }


@router.get("/{document_id}/edited")
def get_edited_pdf_fields(document_id: str):
    _validate_document_id(document_id)
    edited_path = (EDITED_DIR / f"{document_id}.json").resolve()
    try:
        edited_path.relative_to(EDITED_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid edited data path.")

    if not edited_path.exists() or not edited_path.is_file():
        raise HTTPException(status_code=404, detail="No saved edits found for this PDF document.")

    try:
        payload = json.loads(edited_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="Saved edited fields could not be read.")

    return payload
