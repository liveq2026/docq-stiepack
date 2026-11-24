const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

export interface PDFUploadResponse {
  message: string;
  document_id: string;
  filename: string;
  page_count: number;
  character_count: number;
  extracted_text: string;
  analysis_status: "PENDING" | string;
}

export interface PDFAnalysisField {
  name?: string;
  value?: unknown;
  field_type?: string;
  [key: string]: unknown;
}

export interface PDFAnalysisItem {
  [key: string]: unknown;
}

export interface PDFMappingSuggestion {
  document_field?: string;
  suggested_path?: string;
  confidence?: number;
  [key: string]: unknown;
}

export interface PDFAnalysisResult {
  document_type?: string;
  document_mode?: string;
  confidence?: number;
  customer_name?: string;
  document_number?: string;
  document_date?: string;
  fields?: PDFAnalysisField[];
  items?: PDFAnalysisItem[];
  total_amount?: number | string;
  mapping_suggestions?: PDFMappingSuggestion[];
  [key: string]: unknown;
}

export interface PDFAnalyzeResponse {
  message: string;
  document_id: string;
  analysis_status: string;
  analysis: PDFAnalysisResult;
}


export async function uploadPDFDocument(file: File): Promise<PDFUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/pdf-documents/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let message = `Upload failed (${response.status})`;
    try {
      const errorBody = await response.json();
      if (typeof errorBody.detail === "string") message = errorBody.detail;
    } catch {
      // Keep the default status-based message if the response is not JSON.
    }
    throw new Error(message);
  }


  return response.json() as Promise<PDFUploadResponse>;
}


export async function analyzePDFDocument(
  documentId: string,
): Promise<PDFAnalyzeResponse> {
  const response = await fetch(
    `${API_BASE_URL}/pdf-documents/${encodeURIComponent(documentId)}/analyze`,
    { method: "POST" },
  );

  if (!response.ok) {
    let message = `Analysis failed (${response.status})`;
    try {
      const errorBody = await response.json();
      if (typeof errorBody.detail === "string") message = errorBody.detail;
    } catch {
      // Keep the default status-based message if the response is not JSON.
    }
    throw new Error(message);
  }

  return response.json() as Promise<PDFAnalyzeResponse>;
}


export interface PDFEditedField {
  name: string;
  field_type: string;
  value: string;
}

export interface PDFEditedFieldsResponse {
  document_id: string;
  fields: PDFEditedField[];
}

export async function saveEditedPDFFields(
  documentId: string,
  fields: PDFEditedField[],
): Promise<PDFEditedFieldsResponse> {
  const response = await fetch(
    `${API_BASE_URL}/pdf-documents/${encodeURIComponent(documentId)}/edited`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields }),
    },
  );

  if (!response.ok) {
    let message = `Saving edits failed (${response.status})`;
    try {
      const errorBody = await response.json();
      if (typeof errorBody.detail === "string") message = errorBody.detail;
    } catch {
      // Use the status-based message when the response is not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<PDFEditedFieldsResponse>;
}

export async function getEditedPDFFields(
  documentId: string,
): Promise<PDFEditedFieldsResponse | null> {
  const response = await fetch(
    `${API_BASE_URL}/pdf-documents/${encodeURIComponent(documentId)}/edited`,
  );
  if (response.status === 404) return null;
  if (!response.ok) {
    let message = `Loading saved edits failed (${response.status})`;
    try {
      const errorBody = await response.json();
      if (typeof errorBody.detail === "string") message = errorBody.detail;
    } catch {
      // Use the status-based message when the response is not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<PDFEditedFieldsResponse>;
}


export interface PDFGenerateResponse {
  message: string;
  document_id: string;
  generated_filename: string;
  download_url: string;
  applied_changes?: Array<Record<string, unknown>>;
  blank_fields_filled?: Array<Record<string, unknown>>;
  unmatched_fields?: Array<Record<string, unknown>>;
}

export async function generateEditedPDF(documentId: string): Promise<PDFGenerateResponse> {
  const response = await fetch(`${API_BASE_URL}/pdf-documents/${encodeURIComponent(documentId)}/generate`, { method: "POST" });
  if (!response.ok) {
    let message = `PDF generation failed (${response.status})`;
    try { const errorBody = await response.json(); if (typeof errorBody.detail === "string") message = errorBody.detail; } catch { /* status fallback */ }
    throw new Error(message);
  }
  return response.json() as Promise<PDFGenerateResponse>;
}

export async function downloadGeneratedPDF(documentId: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/pdf-documents/${encodeURIComponent(documentId)}/generated`);
  if (!response.ok) {
    let message = `PDF download failed (${response.status})`;
    try { const errorBody = await response.json(); if (typeof errorBody.detail === "string") message = errorBody.detail; } catch { /* status fallback */ }
    throw new Error(message);
  }
  return response.blob();
}
