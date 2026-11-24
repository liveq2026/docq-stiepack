from pathlib import Path
import fitz


def extract_digital_pdf_text(pdf_path: str) -> dict:
    """Extract selectable text from a PDF and reject image-only/scanned PDFs."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    document = fitz.open(path)
    page_texts = []
    total_chars = 0

    try:
        for page_index, page in enumerate(document):
            text = (page.get_text("text") or "").strip()
            page_texts.append({"page": page_index + 1, "text": text, "characters": len(text)})
            total_chars += len(text)
    finally:
        document.close()

    # A scanned/image-only PDF normally has no selectable text. A small amount of
    # metadata/footer text can exist, so use a modest threshold to avoid accepting it.
    if total_chars < 30:
        raise ValueError(
            "This PDF appears to be scanned or contains too little selectable text. "
            "Scanned PDF support will be added in a future version. Please upload a digital PDF."
        )

    combined_text = "\n\n".join(
        f"--- Page {item['page']} ---\n{item['text']}"
        for item in page_texts if item["text"]
    )

    return {
        "text": combined_text,
        "page_count": len(page_texts),
        "character_count": total_chars,
        "pages": page_texts,
    }
