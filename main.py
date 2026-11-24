from pathlib import Path
import shutil
import uuid

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException
)

from pydantic import BaseModel
from fastapi.openapi.utils import get_openapi
from app.document_extractor import extract_docx_text
from app.document_router import route_document
from app.gemini_service import (
    test_gemini,
    analyze_document
)
from app.schemas import DocumentMappingRequest
from app.mapping_service import resolve_mappings
from app.generation_service import generate_document
from app.editor_document_service import (
    load_editor_html,
    save_editor_html,
)
from app.template_service import (
    create_template_copy,
    apply_bindings
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.table_binding_service import discover_table_bindings
from app.expression_html_service import render_expression_html
from fastapi.responses import FileResponse
from app.pdf_signature_router import router as pdf_signature_router
from app.pdf_document_router import router as pdf_document_router

# ---------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------

app = FastAPI(
    title="DocQ",
    description="AI Document Automation Platform",
    version="0.1.0"
)
app.openapi_version = "3.0.3"

# Independent PDF Signature Marker module (DOCX routes remain unchanged).
app.include_router(pdf_signature_router)
app.include_router(pdf_document_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-DocQ-Signature-Areas-Found"],
)

# ---------------------------------------------------------
# Request Model
# ---------------------------------------------------------

class DocumentRequest(BaseModel):
    text: str
    
class DocumentPreviewRequest(BaseModel):
    data: dict
    html: str | None = None


class DocumentGenerateRequest(BaseModel):
    data: dict


class DocumentEditorSaveRequest(BaseModel):
    html: str

# ---------------------------------------------------------
# Root
# ---------------------------------------------------------

@app.get("/")
def root():

    return {
        "application": "DocQ",
        "status": "running"
    }


# ---------------------------------------------------------
# Gemini Test
# ---------------------------------------------------------

@app.get("/test-gemini")
def test_gemini_connection():

    return {
        "message": test_gemini()
    }


# ---------------------------------------------------------
# Text Analysis
# ---------------------------------------------------------

@app.post("/api/v1/documents/analyze")
def analyze_document_endpoint(
    request: DocumentRequest
):

    result = analyze_document(
        request.text
    )

    return result


# ---------------------------------------------------------
# Single DOCX Upload
# ---------------------------------------------------------

@app.post("/api/v1/documents/upload")
async def upload_document(
    file: UploadFile = File(...)
):

    if not file.filename:

        raise HTTPException(
            status_code=400,
            detail="File name is required"
        )

    if not file.filename.lower().endswith(".docx"):

        raise HTTPException(
            status_code=400,
            detail="Only .docx files are supported"
        )

    upload_folder = Path(
        "storage/uploads"
    )

    upload_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    file_id = uuid.uuid4().hex

    temp_file = (
        upload_folder
        / f"{file_id}_{file.filename}"
    )

    with temp_file.open("wb") as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )

    try:

        document_text = extract_docx_text(
            str(temp_file)
        )

        if not document_text.strip():

            raise HTTPException(
                status_code=400,
                detail="The document contains no readable text"
            )

        analysis = analyze_document(
            document_text
        )

        final_path = route_document(
            str(temp_file),
            analysis
        )

        return {
            "message": "Document uploaded and analyzed successfully",
            "filename": file.filename,
            "document_mode": analysis.document_mode,
            "document_type": analysis.document_type,
            "confidence": analysis.confidence,
            "stored_path": final_path,
            "analysis": analysis
        }

    except HTTPException:

        raise

    except Exception as error:

        if temp_file.exists():
            temp_file.unlink()

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# ---------------------------------------------------------
# Bulk DOCX Upload
# ---------------------------------------------------------

@app.post("/api/v1/documents/upload-bulk")
async def upload_bulk_documents(
    files: list[UploadFile] = File(...)
):

    if not files:

        raise HTTPException(
            status_code=400,
            detail="At least one file is required"
        )

    results = []

    upload_folder = Path(
        "storage/uploads"
    )

    upload_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    # -----------------------------------------------------
    # Process every file independently
    # -----------------------------------------------------

    for file in files:

        filename = file.filename or ""

        # -------------------------------------------------
        # Validate extension
        # -------------------------------------------------

        if not filename.lower().endswith(".docx"):

            results.append({
                "filename": filename,
                "status": "FAILED",
                "error": "Only .docx files are supported"
            })

            continue

        file_id = uuid.uuid4().hex

        temp_file = (
            upload_folder
            / f"{file_id}_{filename}"
        )

        try:

            # ---------------------------------------------
            # Save uploaded file
            # ---------------------------------------------

            with temp_file.open("wb") as buffer:

                shutil.copyfileobj(
                    file.file,
                    buffer
                )

            # ---------------------------------------------
            # Extract document text
            # ---------------------------------------------

            document_text = extract_docx_text(
                str(temp_file)
            )

            if not document_text.strip():

                raise ValueError(
                    "The document contains no readable text"
                )

            # ---------------------------------------------
            # Gemini analysis
            # ---------------------------------------------

            analysis = analyze_document(
                document_text
            )

            # ---------------------------------------------
            # Route document
            # ---------------------------------------------

            final_path = route_document(
                str(temp_file),
                analysis
            )

            # ---------------------------------------------
            # Success
            # ---------------------------------------------

            results.append({
                "filename": filename,
                "status": "SUCCESS",
                "document_mode": analysis.document_mode,
                "document_type": analysis.document_type,
                "confidence": analysis.confidence,
                "stored_path": final_path,
                "analysis": analysis
            })

        except Exception as error:

            # ---------------------------------------------
            # Failure should not stop other files
            # ---------------------------------------------

            if temp_file.exists():

                temp_file.unlink()

            results.append({
                "filename": filename,
                "status": "FAILED",
                "error": str(error)
            })

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    successful = sum(
        1
        for result in results
        if result["status"] == "SUCCESS"
    )

    failed = sum(
        1
        for result in results
        if result["status"] == "FAILED"
    )

    return {
        "message": "Bulk document processing completed",
        "total_files": len(files),
        "successful": successful,
        "failed": failed,
        "results": results
    }
    
@app.get("/api/v1/documents")
def list_documents():
    base_storage = Path("storage")

    folders = {
        "DYNAMIC": base_storage / "dynamic",
        "STATIC": base_storage / "static",
        "REVIEW": base_storage / "review",
    }

    documents = []

    for mode, folder in folders.items():
        folder.mkdir(parents=True, exist_ok=True)

        for file_path in sorted(folder.iterdir()):
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() != ".docx":
                continue

            documents.append({
                "filename": file_path.name,
                "document_type": "DOCX",
                "document_mode": mode,
                "size_bytes": file_path.stat().st_size,
            })

    return {
        "documents": documents,
        "total": len(documents),
    }
    
# ---------------------------------------------------------
# List Dynamic Documents
# ---------------------------------------------------------

@app.get("/api/v1/documents/dynamic")
def list_dynamic_documents():

    dynamic_folder = Path(
        "storage/dynamic"
    )

    dynamic_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    documents = []

    for file_path in dynamic_folder.iterdir():

        if not file_path.is_file():
            continue

        if file_path.suffix.lower() != ".docx":
            continue

        documents.append({
            "filename": file_path.name,
            "document_type": "dynamic",
            "path": str(file_path)
        })

    return {
        "total_documents": len(documents),
        "documents": documents
    }
    
# ---------------------------------------------------------
# Open Dynamic Document
# ---------------------------------------------------------

@app.get("/api/v1/documents/dynamic/{filename}")
def open_dynamic_document(filename: str):
    dynamic_folder = Path("storage/dynamic").resolve()
    file_path = (dynamic_folder / filename).resolve()

    # -----------------------------------------------------
    # Security: prevent path traversal
    # -----------------------------------------------------

    try:
        file_path.relative_to(dynamic_folder)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid document path",
        )

    # -----------------------------------------------------
    # Validate document
    # -----------------------------------------------------

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Dynamic document not found",
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Document is not a file",
        )

    if file_path.suffix.lower() != ".docx":
        raise HTTPException(
            status_code=400,
            detail="Only DOCX documents are supported",
        )

    # -----------------------------------------------------
    # Return the actual DOCX binary
    # -----------------------------------------------------

    return FileResponse(
        path=str(file_path),
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        filename=file_path.name,
    )
    
# ---------------------------------------------------------
# Open Static Document
# ---------------------------------------------------------

@app.get("/api/v1/documents/static/{filename}")
def open_static_document(filename: str):
    static_folder = Path("storage/static").resolve()
    file_path = (static_folder / filename).resolve()

    # -----------------------------------------------------
    # Security: prevent path traversal
    # -----------------------------------------------------

    try:
        file_path.relative_to(static_folder)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid document path",
        )

    # -----------------------------------------------------
    # Validate document
    # -----------------------------------------------------

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Static document not found",
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Document is not a file",
        )

    if file_path.suffix.lower() != ".docx":
        raise HTTPException(
            status_code=400,
            detail="Only DOCX documents are supported",
        )

    # -----------------------------------------------------
    # Return the actual DOCX binary
    # -----------------------------------------------------

    return FileResponse(
        path=str(file_path),
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        filename=file_path.name,
    )
    
# ---------------------------------------------------------
# Discover Dynamic Fields
# ---------------------------------------------------------

@app.post("/api/v1/documents/dynamic/{filename}/discover-fields")
def discover_dynamic_fields(
    filename: str
):

    dynamic_folder = Path(
        "storage/dynamic"
    )

    file_path = dynamic_folder / filename

    # -----------------------------------------------------
    # Security: prevent path traversal
    # -----------------------------------------------------

    try:

        file_path = file_path.resolve()
        dynamic_folder = dynamic_folder.resolve()

        file_path.relative_to(
            dynamic_folder
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid document path"
        )

    # -----------------------------------------------------
    # Validate document
    # -----------------------------------------------------

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Dynamic document not found"
        )

    if not file_path.is_file():

        raise HTTPException(
            status_code=404,
            detail="Document is not a file"
        )

    if file_path.suffix.lower() != ".docx":

        raise HTTPException(
            status_code=400,
            detail="Only DOCX documents are supported"
        )

    # -----------------------------------------------------
    # Extract document content
    # -----------------------------------------------------

    document_text = extract_docx_text(
        str(file_path)
    )

    if not document_text.strip():

        raise HTTPException(
            status_code=400,
            detail="The document contains no readable text"
        )

    # -----------------------------------------------------
    # Ask Gemini to discover dynamic fields
    # -----------------------------------------------------

    analysis = analyze_document(
        document_text
    )

    # -----------------------------------------------------
    # Discover structural repeating tables
    # -----------------------------------------------------

    table_bindings = discover_table_bindings(
        str(file_path)
    )

    # -----------------------------------------------------
    # Return discovered fields + tables
    # -----------------------------------------------------

    return {
        "filename": file_path.name,

        "document_type":
            analysis.document_type,

        "document_mode":
            analysis.document_mode,

        "confidence":
            analysis.confidence,

        "fields":
            analysis.fields,

        "items":
            analysis.items,

        "mapping_suggestions":
            analysis.mapping_suggestions,

        "table_bindings":
            table_bindings
    }
    
# ---------------------------------------------------------
# Save Dynamic Document Mapping
# ---------------------------------------------------------

@app.post("/api/v1/documents/dynamic/{filename}/mapping")
def save_document_mapping(
    filename: str,
    request: DocumentMappingRequest
):

    dynamic_folder = Path(
        "storage/dynamic"
    )

    file_path = dynamic_folder / filename

    # -----------------------------------------------------
    # Security: prevent path traversal
    # -----------------------------------------------------

    try:

        file_path = file_path.resolve()
        dynamic_folder = dynamic_folder.resolve()

        file_path.relative_to(
            dynamic_folder
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid document path"
        )

    # -----------------------------------------------------
    # Validate document
    # -----------------------------------------------------

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Dynamic document not found"
        )

    if file_path.suffix.lower() != ".docx":

        raise HTTPException(
            status_code=400,
            detail="Only DOCX documents are supported"
        )

    # -----------------------------------------------------
    # Mapping storage
    # -----------------------------------------------------

    mapping_folder = Path(
        "storage/mappings"
    )

    mapping_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    mapping_file = (
        mapping_folder
        / f"{file_path.stem}.json"
    )

    # -----------------------------------------------------
    # Save mapping
    # -----------------------------------------------------

    import json

    mapping_data = {
        "filename": file_path.name,
        "mappings": [
            mapping.model_dump()
            for mapping in request.mappings
        ]
    }

    with mapping_file.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            mapping_data,
            file,
            indent=2,
            ensure_ascii=False
        )

    return {
        "message": "Document mapping saved successfully",
        "filename": file_path.name,
        "mapping_file": str(mapping_file),
        "mappings": mapping_data["mappings"]
    }
    
# ---------------------------------------------------------
# Preview Dynamic Document
# ---------------------------------------------------------

@app.post(
    "/api/v1/documents/dynamic/{filename}/preview"
)
def preview_dynamic_document(
    filename: str,
    request: DocumentPreviewRequest
):

    dynamic_folder = Path(
        "storage/dynamic"
    )

    file_path = dynamic_folder / filename

    # -----------------------------------------------------
    # Security
    # -----------------------------------------------------

    try:

        file_path = file_path.resolve()
        dynamic_folder = dynamic_folder.resolve()

        file_path.relative_to(
            dynamic_folder
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid document path"
        )

    # -----------------------------------------------------
    # Validate document
    # -----------------------------------------------------

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Dynamic document not found"
        )

    if file_path.suffix.lower() != ".docx":

        raise HTTPException(
            status_code=400,
            detail="Only DOCX documents are supported"
        )

    # -----------------------------------------------------
    # Load saved mapping
    # -----------------------------------------------------

    mapping_folder = Path(
        "storage/mappings"
    )

    mapping_file = (
        mapping_folder
        / f"{file_path.stem}.json"
    )

    if not mapping_file.exists():

        raise HTTPException(
            status_code=404,
            detail="Mapping not found for this document"
        )

    import json

    with mapping_file.open(
        "r",
        encoding="utf-8"
    ) as file:

        mapping_data = json.load(file)

    mappings = mapping_data.get(
        "mappings",
        []
    )

    # -----------------------------------------------------
    # Resolve runtime data
    # -----------------------------------------------------

    resolved_fields = resolve_mappings(
        runtime_data=request.data,
        mappings=mappings
    )

    # -----------------------------------------------------
    # Return preview
    # -----------------------------------------------------

    response = {
        "filename": file_path.name,
        "status": "PREVIEW_READY",
        "resolved_fields": resolved_fields
    }

    if request.html and request.html.strip():
        response["rendered_html"] = render_expression_html(
            request.html,
            request.data,
        )

    return response
    
# ---------------------------------------------------------
# Create DocQ Template
# ---------------------------------------------------------

@app.post(
    "/api/v1/documents/dynamic/{filename}/create-template"
)
def create_document_template(
    filename: str
):

    dynamic_folder = Path(
        "storage/dynamic"
    )

    file_path = dynamic_folder / filename

    try:

        file_path = file_path.resolve()
        dynamic_folder = dynamic_folder.resolve()

        file_path.relative_to(
            dynamic_folder
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid document path"
        )

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Dynamic document not found"
        )

    if file_path.suffix.lower() != ".docx":

        raise HTTPException(
            status_code=400,
            detail="Only DOCX documents are supported"
        )

    # -----------------------------------------------------
    # Load saved mapping
    # -----------------------------------------------------

    import json

    mapping_folder = Path(
        "storage/mappings"
    )

    mapping_file = (
        mapping_folder
        / f"{file_path.stem}.json"
    )

    if not mapping_file.exists():

        raise HTTPException(
            status_code=404,
            detail="Mapping not found for this document"
        )

    with mapping_file.open(
        "r",
        encoding="utf-8"
    ) as file:

        mapping_data = json.load(file)

    mappings = mapping_data.get(
        "mappings",
        []
    )

    # -----------------------------------------------------
    # Create template copy
    # -----------------------------------------------------

    template_path = create_template_copy(
        source_file=str(file_path),
        mappings=mappings
    )

    # -----------------------------------------------------
    # Apply DocQ bindings
    # -----------------------------------------------------

    template_path = apply_bindings(
        template_file=template_path,
        mappings=mappings
    )

    return {
        "message": "DocQ template created successfully",
        "source_file": file_path.name,
        "template_file": template_path,
        "bindings_applied": len(mappings)
    }

# ---------------------------------------------------------
# Editor Document Persistence
# ---------------------------------------------------------

@app.get("/api/v1/documents/dynamic/{filename}/editor")
def get_editor_document(filename: str):
    dynamic_folder = Path("storage/dynamic").resolve()
    file_path = (dynamic_folder / filename).resolve()

    try:
        file_path.relative_to(dynamic_folder)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document path")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Dynamic document not found")

    html = load_editor_html(file_path.name)
    return {
        "filename": file_path.name,
        "saved": html is not None,
        "html": html or "",
    }


@app.put("/api/v1/documents/dynamic/{filename}/editor")
def save_editor_document(
    filename: str,
    request: DocumentEditorSaveRequest,
):
    dynamic_folder = Path("storage/dynamic").resolve()
    file_path = (dynamic_folder / filename).resolve()

    try:
        file_path.relative_to(dynamic_folder)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document path")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Dynamic document not found")

    if file_path.suffix.lower() != ".docx":
        raise HTTPException(status_code=400, detail="Only DOCX documents are supported")

    if not request.html.strip():
        raise HTTPException(status_code=400, detail="Editor HTML cannot be empty")

    editor_file = save_editor_html(file_path.name, request.html)

    return {
        "message": "Editor document saved successfully",
        "filename": file_path.name,
        "editor_file": editor_file,
    }
    

# ---------------------------------------------------------
# Static Editor Document Persistence
# ---------------------------------------------------------

@app.get("/api/v1/documents/static/{filename}/editor")
def get_static_editor_document(filename: str):
    static_folder = Path("storage/static").resolve()
    file_path = (static_folder / filename).resolve()

    try:
        file_path.relative_to(static_folder)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid document path"
        )

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Static document not found"
        )

    if file_path.suffix.lower() != ".docx":
        raise HTTPException(
            status_code=400,
            detail="Only DOCX documents are supported"
        )

    html = load_editor_html(file_path.name)

    return {
        "filename": file_path.name,
        "saved": html is not None,
        "html": html or "",
    }


@app.put("/api/v1/documents/static/{filename}/editor")
def save_static_editor_document(
    filename: str,
    request: DocumentEditorSaveRequest,
):
    static_folder = Path("storage/static").resolve()
    file_path = (static_folder / filename).resolve()

    try:
        file_path.relative_to(static_folder)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid document path"
        )

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Static document not found"
        )

    if file_path.suffix.lower() != ".docx":
        raise HTTPException(
            status_code=400,
            detail="Only DOCX documents are supported"
        )

    if not request.html.strip():
        raise HTTPException(
            status_code=400,
            detail="Editor HTML cannot be empty"
        )

    editor_file = save_editor_html(file_path.name, request.html)

    return {
        "message": "Static editor document saved successfully",
        "filename": file_path.name,
        "editor_file": editor_file,
    }


# ---------------------------------------------------------
# Static Document Preview
# ---------------------------------------------------------

@app.post("/api/v1/documents/static/{filename}/preview")
def preview_static_document(
    filename: str,
    request: DocumentPreviewRequest,
):
    static_folder = Path("storage/static").resolve()
    file_path = (static_folder / filename).resolve()

    try:
        file_path.relative_to(static_folder)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document path")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Static document not found")
    if file_path.suffix.lower() != ".docx":
        raise HTTPException(status_code=400, detail="Only DOCX documents are supported")

    editor_html = request.html or load_editor_html(file_path.name)
    if not editor_html or not editor_html.strip():
        raise HTTPException(
            status_code=400,
            detail="Please open and save this document in Editor before previewing",
        )

    return {
        "filename": file_path.name,
        "status": "PREVIEW_READY",
        "rendered_html": render_expression_html(editor_html, request.data),
    }


# ---------------------------------------------------------
# Generate Final Static DOCX
# ---------------------------------------------------------

@app.post("/api/v1/documents/static/{filename}/generate")
def generate_static_document(
    filename: str,
    request: DocumentGenerateRequest,
):
    static_folder = Path("storage/static").resolve()
    file_path = (static_folder / filename).resolve()

    try:
        file_path.relative_to(static_folder)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document path")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Static document not found")
    if file_path.suffix.lower() != ".docx":
        raise HTTPException(status_code=400, detail="Only DOCX documents are supported")

    editor_html = load_editor_html(file_path.name)
    if not editor_html:
        raise HTTPException(
            status_code=400,
            detail="Please save the document in Editor before generating",
        )

    generated_folder = Path("storage/generated")
    generated_folder.mkdir(parents=True, exist_ok=True)
    output_file = generated_folder / f"{file_path.stem}_{uuid.uuid4().hex[:8]}.docx"

    try:
        result = generate_document(
            source_file=str(file_path),
            output_file=str(output_file),
            mappings=[],
            runtime_data=request.data,
            editor_html=editor_html,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Static document generation failed: {exc}",
        )

    return FileResponse(
        path=result["output_file"],
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        filename=output_file.name,
        headers={
            "X-DocQ-Signature-Areas-Found": str(result.get("signature_areas_found", 0)),
        },
    )


# ---------------------------------------------------------
# Generate Final DOCX
# ---------------------------------------------------------

@app.post(
    "/api/v1/documents/dynamic/{filename}/generate"
)
def generate_dynamic_document(
    filename: str,
    request: DocumentGenerateRequest
):

    dynamic_folder = Path(
        "storage/dynamic"
    )

    file_path = dynamic_folder / filename

    # -----------------------------------------------------
    # Security
    # -----------------------------------------------------

    try:

        file_path = file_path.resolve()
        dynamic_folder = dynamic_folder.resolve()

        file_path.relative_to(
            dynamic_folder
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid document path"
        )

    # -----------------------------------------------------
    # Validate source document
    # -----------------------------------------------------

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Dynamic document not found"
        )

    if not file_path.is_file():

        raise HTTPException(
            status_code=404,
            detail="Document is not a file"
        )

    if file_path.suffix.lower() != ".docx":

        raise HTTPException(
            status_code=400,
            detail="Only DOCX documents are supported"
        )

    # -----------------------------------------------------
    # Load saved mapping
    # -----------------------------------------------------

    import json

    mapping_file = (
        Path("storage/mappings")
        / f"{file_path.stem}.json"
    )

    if not mapping_file.exists():

        raise HTTPException(
            status_code=404,
            detail="Mapping not found for this document"
        )

    with mapping_file.open(
        "r",
        encoding="utf-8"
    ) as file:

        mapping_data = json.load(file)

    mappings = mapping_data.get(
        "mappings",
        []
    )

    if not mappings:

        raise HTTPException(
            status_code=400,
            detail="No mappings configured for this document"
        )

    # -----------------------------------------------------
    # Create unique generated output
    # -----------------------------------------------------

    generated_folder = Path(
        "storage/generated"
    )

    generated_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = (
        generated_folder
        / f"{file_path.stem}_{uuid.uuid4().hex[:8]}.docx"
    )

    # -----------------------------------------------------
    # Generate final populated DOCX
    # -----------------------------------------------------

    try:

        result = generate_document(
            source_file=str(file_path),
            output_file=str(output_file),
            mappings=mappings,
            runtime_data=request.data,
            editor_html=load_editor_html(file_path.name),
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Document generation failed: {exc}"
        )

    return FileResponse(
        path=result["output_file"],
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        filename=output_file.name,
        headers={
            "X-DocQ-Replaced-Fields": str(
                result["replaced_fields"]
            ),
            "X-DocQ-Rendered-Tables": str(
                result["rendered_tables"]
            ),
            "X-DocQ-Items-Rendered": str(
                result["items_rendered"]
            ),
            "X-DocQ-Signature-Areas-Found": str(
                result.get("signature_areas_found", 0)
            ),
        },
    )
    
# ---------------------------------------------------------
# Custom OpenAPI schema
# ---------------------------------------------------------

def custom_openapi():

    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="DocQ",
        version="0.1.0",
        description="AI Document Automation Platform",
        routes=app.routes,
    )

    # Use OpenAPI 3.0 for Swagger file-upload compatibility
    openapi_schema["openapi"] = "3.0.3"

    # -----------------------------------------------------
    # Force bulk upload files to be binary file array
    # -----------------------------------------------------

    bulk_path = openapi_schema.get(
        "paths",
        {}
    ).get(
        "/api/v1/documents/upload-bulk"
    )

    if bulk_path:

        post_operation = bulk_path.get("post")

        if post_operation:

            request_body = post_operation.get(
                "requestBody"
            )

            if request_body:

                multipart = request_body.get(
                    "content",
                    {}
                ).get(
                    "multipart/form-data"
                )

                if multipart:

                    multipart["schema"] = {
                        "type": "object",
                        "required": [
                            "files"
                        ],
                        "properties": {
                            "files": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "format": "binary"
                                }
                            }
                        }
                    }
                    
                        # -----------------------------------------------------
    # Force single upload file to binary
    # -----------------------------------------------------

    single_path = openapi_schema.get(
        "paths",
        {}
    ).get(
        "/api/v1/documents/upload"
    )

    if single_path:

        post_operation = single_path.get("post")

        if post_operation:

            request_body = post_operation.get(
                "requestBody"
            )

            if request_body:

                multipart = request_body.get(
                    "content",
                    {}
                ).get(
                    "multipart/form-data"
                )

                if multipart:

                    multipart["schema"] = {
                        "type": "object",
                        "required": [
                            "file"
                        ],
                        "properties": {
                            "file": {
                                "type": "string",
                                "format": "binary"
                            }
                        }
                    }
                    
        # -----------------------------------------------------
    # Force PDF Signature Upload to binary file
    # -----------------------------------------------------

    pdf_path = openapi_schema.get(
        "paths", {}
    ).get(
        "/api/v1/pdf-signatures/upload"
    )

    if pdf_path:
        post_operation = pdf_path.get("post")

        if post_operation:
            request_body = post_operation.get("requestBody")

            if request_body:
                multipart = request_body.get(
                    "content", {}
                ).get("multipart/form-data")

                if multipart:
                    multipart["schema"] = {
                        "type": "object",
                        "required": ["file"],
                        "properties": {
                            "file": {
                                "type": "string",
                                "format": "binary"
                            }
                        }
                    }
                    
        # -----------------------------------------------------
    # Force PDF Documents Upload to binary file
    # -----------------------------------------------------

    pdf_documents_path = openapi_schema.get(
        "paths", {}
    ).get(
        "/api/v1/pdf-documents/upload"
    )

    if pdf_documents_path:
        post_operation = pdf_documents_path.get("post")

        if post_operation:
            request_body = post_operation.get("requestBody")

            if request_body:
                multipart = request_body.get(
                    "content", {}
                ).get("multipart/form-data")

                if multipart:
                    multipart["schema"] = {
                        "type": "object",
                        "required": ["file"],
                        "properties": {
                            "file": {
                                "type": "string",
                                "format": "binary"
                            }
                        }
                    }

    app.openapi_schema = openapi_schema

    return app.openapi_schema


app.openapi = custom_openapi