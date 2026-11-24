import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Paper,
  Stack,
  Typography,
  Divider,
  TextField,
} from "@mui/material";
import PictureAsPdfOutlinedIcon from "@mui/icons-material/PictureAsPdfOutlined";
import CloudUploadOutlinedIcon from "@mui/icons-material/CloudUploadOutlined";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import {
  analyzePDFDocument,
  uploadPDFDocument,
  saveEditedPDFFields,
  getEditedPDFFields,
  generateEditedPDF,
  downloadGeneratedPDF,
  type PDFUploadResponse,
  type PDFAnalyzeResponse,
} from "../api/pdfDocumentApi";


function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}


export default function PDFDocumentWorkspace() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<PDFUploadResponse | null>(null);
  const [analysisResult, setAnalysisResult] = useState<PDFAnalyzeResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [analysisError, setAnalysisError] = useState("");
  const [showExtractedText, setShowExtractedText] = useState(false);
  const [editedFields, setEditedFields] = useState<Array<{ name: string; value: string; field_type: string }>>([]);
  const [editsSaved, setEditsSaved] = useState(false);
  const [savingEdits, setSavingEdits] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [generatingPDF, setGeneratingPDF] = useState(false);
  const [generatedPDF, setGeneratedPDF] = useState(false);
  const [generateError, setGenerateError] = useState("");
  const [generateSummary, setGenerateSummary] = useState("");
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [previewPage, setPreviewPage] = useState(1);
  const [previewZoom, setPreviewZoom] = useState(100);

  useEffect(() => {
    if (!selectedFile) {
      setPdfPreviewUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(selectedFile);
    setPdfPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [selectedFile]);

  const handleFile = (file?: File) => {
    setError("");
    setAnalysisError("");
    setUploadResult(null);
    setAnalysisResult(null);
    setGeneratedPDF(false);
    setGenerateError("");
    setGenerateSummary("");
    setPreviewPage(1);
    setPreviewZoom(100);
    if (!file) return;
    if (
      !file.name.toLowerCase().endsWith(".pdf") ||
      (file.type && file.type !== "application/pdf")
    ) {
      setSelectedFile(null);
      setError("Please select a PDF file.");
      return;
    }
    setSelectedFile(file);
  };


  const handleUpload = async () => {
    if (!selectedFile) return;
    setError("");
    setUploading(true);
    try {
      const result = await uploadPDFDocument(selectedFile);
      setUploadResult(result);
      setAnalysisResult(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to upload PDF. Please try again.",
      );
    } finally {
      setUploading(false);
    }
  };


  const handleAnalyze = async () => {
    if (!uploadResult?.document_id) return;
    setAnalysisError("");
    setAnalyzing(true);
    try {
      const result = await analyzePDFDocument(uploadResult.document_id);
      setAnalysisResult(result);
      const aiFields = (result.analysis?.fields ?? []).map((field) => ({
        name: String(field.name ?? ""),
        value: field.value === null || field.value === undefined ? "" : typeof field.value === "string" ? field.value : JSON.stringify(field.value),
        field_type: String(field.field_type ?? "string"),
      }));
      setEditedFields(aiFields);
      setEditsSaved(false);
      setSaveError("");
      // Restore previously persisted edits, if any. A 404 means this document has not been saved yet.
      try {
        const saved = await getEditedPDFFields(uploadResult.document_id);
        if (saved?.fields) {
          setEditedFields(saved.fields.map((field) => ({
            name: String(field.name ?? ""),
            value: field.value === null || field.value === undefined ? "" : String(field.value),
            field_type: String(field.field_type ?? "string"),
          })));
          setEditsSaved(true);
        }
      } catch (restoreError) {
        setSaveError(restoreError instanceof Error ? restoreError.message : "Unable to restore saved edits.");
      }
    } catch (err) {
      setAnalysisError(
        err instanceof Error ? err.message : "Unable to analyze PDF. Please try again.",
      );
    } finally {
      setAnalyzing(false);
    }
  };


  const handleSaveEdits = async () => {
    if (!uploadResult?.document_id) return;
    setSavingEdits(true);
    setSaveError("");
    setEditsSaved(false);
    try {
      await saveEditedPDFFields(uploadResult.document_id, editedFields);
      setEditsSaved(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Unable to save edits.");
    } finally {
      setSavingEdits(false);
    }
  };

  const handleGeneratePDF = async () => {
    if (!uploadResult?.document_id) return;
    setGeneratingPDF(true); setGenerateError(""); setGenerateSummary("");
    try {
      await saveEditedPDFFields(uploadResult.document_id, editedFields);
      setEditsSaved(true);
      const result = await generateEditedPDF(uploadResult.document_id);
      const filledCount = result.blank_fields_filled?.length ?? 0;
      const replacementCount = result.applied_changes?.length ?? 0;
      const unmatchedCount = result.unmatched_fields?.length ?? 0;
      setGenerateSummary(`Generated ${result.generated_filename}. Blank fields filled: ${filledCount}; text replacements: ${replacementCount}; unmatched: ${unmatchedCount}.`);
      setGeneratedPDF(true);
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : "Unable to generate PDF.");
    } finally { setGeneratingPDF(false); }
  };

  const handleDownloadGeneratedPDF = async () => {
    if (!uploadResult?.document_id) return;
    setGenerateError("");
    try {
      const blob = await downloadGeneratedPDF(uploadResult.document_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${selectedFile?.name.replace(/\.pdf$/i, "") || "document"}_edited.pdf`;
      document.body.appendChild(link); link.click(); link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : "Unable to download generated PDF.");
    }
  };

  const fileSize = selectedFile
    ? selectedFile.size < 1024 * 1024
      ? `${(selectedFile.size / 1024).toFixed(1)} KB`
      : `${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB`
    : "";

  const analysis = analysisResult?.analysis;
  const extractedFields = Array.isArray(analysis?.fields) ? analysis.fields : [];
  const lineItems = Array.isArray(analysis?.items) ? analysis.items : [];
  const mappingSuggestions = Array.isArray(analysis?.mapping_suggestions)
    ? analysis.mapping_suggestions
    : [];

  return (
    <Box sx={{ maxWidth: 1200, mx: "auto" }}>
      <Stack spacing={1} sx={{ mb: 3 }}>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <PictureAsPdfOutlinedIcon color="primary" sx={{ fontSize: 32 }} />
          <Typography variant="h4" fontWeight={700}>PDF Documents</Typography>
          <Chip label="Digital PDFs" color="info" variant="outlined" />
        </Stack>
        <Typography color="text.secondary">
          Upload a digital PDF to extract text, analyze its contents, and edit document fields.
        </Typography>
      </Stack>


      <Paper variant="outlined" sx={{ p: { xs: 2, sm: 4 }, borderRadius: 3 }}>
        <Box
          sx={{
            border: "2px dashed",
            borderColor: selectedFile ? "primary.main" : "divider",
            borderRadius: 3,
            p: { xs: 3, sm: 5 },
            textAlign: "center",
            bgcolor: "action.hover",
          }}
        >
          <CloudUploadOutlinedIcon sx={{ fontSize: 48, color: "primary.main", mb: 1 }} />
          <Typography variant="h6" fontWeight={600}>Upload your PDF document</Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
            Select a digital PDF file from your computer. Scanned PDFs are not supported in this workflow yet.
          </Typography>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            hidden
            onChange={(event) => handleFile(event.target.files?.[0])}
          />
          <Button variant="contained" onClick={() => inputRef.current?.click()} disabled={uploading || analyzing}>
            Choose PDF
          </Button>
          {error && <Alert severity="error" sx={{ mt: 2, textAlign: "left" }}>{error}</Alert>}
        </Box>


        {selectedFile && (
          <Paper variant="outlined" sx={{ mt: 2, p: 2, borderRadius: 2 }}>
            <Stack direction="row" alignItems="center" spacing={2}>
              <PictureAsPdfOutlinedIcon color="error" />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography fontWeight={600} noWrap>{selectedFile.name}</Typography>
                <Typography variant="body2" color="text.secondary">{fileSize}</Typography>
              </Box>
              <Chip label={uploadResult ? "Uploaded" : "Selected"} color="success" size="small" />
            </Stack>
            {!uploadResult && (
              <Button
                variant="contained"
                onClick={handleUpload}
                disabled={uploading}
                startIcon={uploading ? <CircularProgress size={18} color="inherit" /> : <CloudUploadOutlinedIcon />}
                sx={{ mt: 2 }}
              >
                {uploading ? "Uploading PDF..." : "Upload PDF"}
              </Button>
            )}
          </Paper>
        )}
      </Paper>


      {uploadResult && (
        <Paper variant="outlined" sx={{ mt: 2, p: 2.5, borderRadius: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
            <CheckCircleIcon color="success" />
            <Typography variant="h6" fontWeight={600}>PDF uploaded and text extracted successfully</Typography>
          </Stack>
          <Alert severity="success" sx={{ mb: 2 }}>{uploadResult.message}</Alert>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}>
              <Typography variant="caption" color="text.secondary">Document ID</Typography>
              <Typography sx={{ wordBreak: "break-all" }} variant="body2">{uploadResult.document_id}</Typography>
            </Paper>
            <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}>
              <Typography variant="caption" color="text.secondary">Pages</Typography>
              <Typography variant="h6">{uploadResult.page_count}</Typography>
            </Paper>
            <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}>
              <Typography variant="caption" color="text.secondary">Extracted characters</Typography>
              <Typography variant="h6">{uploadResult.character_count.toLocaleString()}</Typography>
            </Paper>
            <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}>
              <Typography variant="caption" color="text.secondary">Analysis status</Typography>
              <Typography variant="h6">{analysisResult?.analysis_status ?? uploadResult.analysis_status}</Typography>
            </Paper>
          </Stack>
          <Button
            onClick={() => setShowExtractedText((previous) => !previous)}
            endIcon={<ExpandMoreIcon sx={{ transform: showExtractedText ? "rotate(180deg)" : "none", transition: "transform .2s" }} />}
            sx={{ mt: 2 }}
          >
            {showExtractedText ? "Hide extracted text" : "View extracted text"}
          </Button>
          <Collapse in={showExtractedText}>
            <Paper variant="outlined" sx={{ mt: 1, p: 2, maxHeight: 320, overflow: "auto", whiteSpace: "pre-wrap" }}>
              <Typography variant="body2">{uploadResult.extracted_text}</Typography>
            </Paper>
          </Collapse>
          <Divider sx={{ my: 2 }} />
          <Button
            variant="contained"
            color="primary"
            onClick={handleAnalyze}
            disabled={analyzing || !!analysisResult}
            startIcon={analyzing ? <CircularProgress size={18} color="inherit" /> : <AutoAwesomeOutlinedIcon />}
          >
            {analyzing ? "Analyzing with AI..." : analysisResult ? "Analysis Completed" : "Analyze Document"}
          </Button>
          {analysisError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {analysisError}
              <Button size="small" onClick={handleAnalyze} disabled={analyzing} sx={{ ml: 1 }}>Retry</Button>
            </Alert>
          )}
        </Paper>
      )}


      {analysisResult && analysis && (
        <Paper variant="outlined" sx={{ mt: 2, p: 2.5, borderRadius: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
            <AutoAwesomeOutlinedIcon color="primary" />
            <Typography variant="h6" fontWeight={700}>AI Analysis Results</Typography>
            <Chip label={analysisResult.analysis_status} color="success" size="small" />
          </Stack>
          <Alert severity="success" sx={{ mb: 2 }}>{analysisResult.message}</Alert>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 2 }}>
            <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}>
              <Typography variant="caption" color="text.secondary">Document type</Typography>
              <Typography variant="h6">{analysis.document_type || "Not detected"}</Typography>
            </Paper>
            <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}>
              <Typography variant="caption" color="text.secondary">Document mode</Typography>
              <Typography variant="h6">{analysis.document_mode || "—"}</Typography>
            </Paper>
            <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}>
              <Typography variant="caption" color="text.secondary">Confidence</Typography>
              <Typography variant="h6">
                {typeof analysis.confidence === "number"
                  ? `${Math.round(analysis.confidence <= 1 ? analysis.confidence * 100 : analysis.confidence)}%`
                  : "—"}
              </Typography>
            </Paper>
          </Stack>
          {(analysis.customer_name || analysis.document_number || analysis.document_date || analysis.total_amount !== undefined) && (
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 2 }}>
              {analysis.customer_name && <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}><Typography variant="caption" color="text.secondary">Customer</Typography><Typography fontWeight={600}>{analysis.customer_name}</Typography></Paper>}
              {analysis.document_number && <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}><Typography variant="caption" color="text.secondary">Document number</Typography><Typography fontWeight={600}>{analysis.document_number}</Typography></Paper>}
              {analysis.document_date && <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}><Typography variant="caption" color="text.secondary">Document date</Typography><Typography fontWeight={600}>{analysis.document_date}</Typography></Paper>}
              {analysis.total_amount !== undefined && <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}><Typography variant="caption" color="text.secondary">Total amount</Typography><Typography fontWeight={600}>{displayValue(analysis.total_amount)}</Typography></Paper>}
            </Stack>
          )}
          <Divider sx={{ my: 2 }} />
          <Stack direction={{ xs: "column", sm: "row" }} alignItems={{ sm: "center" }} justifyContent="space-between" spacing={1} sx={{ mb: 1.5 }}>
            <Typography variant="subtitle1" fontWeight={700}>Review & Edit fields ({editedFields.length})</Typography>
            <Button variant="outlined" size="small" onClick={() => { setEditedFields((prev) => [...prev, { name: "New Field", value: "", field_type: "string" }]); setEditsSaved(false); }}>+ Add Field</Button>
          </Stack>
          {editedFields.length ? (
            <Stack spacing={1.5}>
              {editedFields.map((field, index) => (
                <Paper key={`edit-field-${index}`} variant="outlined" sx={{ p: 1.5 }}>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ md: "center" }}>
                    <TextField label="Field name" size="small" value={field.name} onChange={(event) => { setEditedFields((prev) => prev.map((f, i) => i === index ? { ...f, name: event.target.value } : f)); setEditsSaved(false); }} sx={{ flex: 1 }} />
                    <TextField label="Field type" size="small" value={field.field_type} onChange={(event) => { setEditedFields((prev) => prev.map((f, i) => i === index ? { ...f, field_type: event.target.value } : f)); setEditsSaved(false); }} sx={{ width: { md: 160 } }} />
                    <TextField label="Value" size="small" multiline minRows={1} maxRows={4} value={field.value} onChange={(event) => { setEditedFields((prev) => prev.map((f, i) => i === index ? { ...f, value: event.target.value } : f)); setEditsSaved(false); }} sx={{ flex: 2 }} />
                    <Button color="error" size="small" onClick={() => { setEditedFields((prev) => prev.filter((_, i) => i !== index)); setEditsSaved(false); }}>Remove</Button>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          ) : <Alert severity="info">No fields available. Use Add Field to create one.</Alert>}
          <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
            <Button variant="contained" onClick={handleSaveEdits} disabled={savingEdits || generatingPDF || !uploadResult?.document_id}>{savingEdits ? "Saving…" : "Save Edits"}</Button>
            <Button variant="outlined" onClick={() => { setEditedFields((analysis?.fields ?? []).map((field) => ({ name: String(field.name ?? ""), value: field.value === null || field.value === undefined ? "" : typeof field.value === "string" ? field.value : JSON.stringify(field.value), field_type: String(field.field_type ?? "string") }))); setEditsSaved(false); setGeneratedPDF(false); }}>Reset to AI Results</Button>
          </Stack>
          {editsSaved && <Alert severity="success" sx={{ mt: 1.5 }}>Edited fields saved to the backend successfully.</Alert>}
          {saveError && <Alert severity="error" sx={{ mt: 1.5 }}>{saveError}</Alert>}
          <Divider sx={{ my: 2 }} />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
            <Button variant="contained" color="success" startIcon={generatingPDF ? <CircularProgress size={18} color="inherit" /> : <PictureAsPdfOutlinedIcon />} onClick={handleGeneratePDF} disabled={generatingPDF || savingEdits || !uploadResult?.document_id}>
              {generatingPDF ? "Generating PDF…" : "Generate PDF"}
            </Button>
            {generatedPDF && <Button variant="outlined" onClick={handleDownloadGeneratedPDF}>Download Generated PDF</Button>}
          </Stack>
          {generateSummary && <Alert severity="success" sx={{ mt: 1.5 }}>{generateSummary}</Alert>}
          {generateError && <Alert severity="error" sx={{ mt: 1.5 }}>{generateError}</Alert>}
          {lineItems.length > 0 && (
            <Box sx={{ mt: 3 }}>
              <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>Line items ({lineItems.length})</Typography>
              <Stack spacing={1}>
                {lineItems.map((item, index) => (
                  <Paper key={`item-${index}`} variant="outlined" sx={{ p: 1.5 }}>
                    <Typography variant="subtitle2">Item {index + 1}</Typography>
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{displayValue(item)}</Typography>
                  </Paper>
                ))}
              </Stack>
            </Box>
          )}
          {mappingSuggestions.length > 0 && (
            <Box sx={{ mt: 3 }}>
              <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>Mapping suggestions ({mappingSuggestions.length})</Typography>
              <Stack spacing={1}>
                {mappingSuggestions.map((suggestion, index) => (
                  <Paper key={`suggestion-${index}`} variant="outlined" sx={{ p: 1.5 }}>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
                      <Typography sx={{ flex: 1 }}>{suggestion.document_field || "Document field"}</Typography>
                      <Typography color="primary" sx={{ flex: 1, fontFamily: "monospace" }}>{suggestion.suggested_path || "—"}</Typography>
                      {typeof suggestion.confidence === "number" && <Chip size="small" label={`${Math.round(suggestion.confidence * 100)}% confidence`} />}
                    </Stack>
                  </Paper>
                ))}
              </Stack>
            </Box>
          )}
        </Paper>
      )}



      {uploadResult && selectedFile && pdfPreviewUrl && (
        <Paper variant="outlined" sx={{ mt: 2, p: 2, borderRadius: 2 }}>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            alignItems={{ sm: "center" }}
            justifyContent="space-between"
            spacing={1}
            sx={{ mb: 1.5 }}
          >
            <Box>
              <Typography variant="h6" fontWeight={700}>PDF Preview</Typography>
              <Typography variant="body2" color="text.secondary">
                Review the original uploaded PDF. This preview does not modify the source file.
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Button size="small" variant="outlined" onClick={() => setPreviewZoom((z) => Math.max(50, z - 10))} disabled={previewZoom <= 50}>− Zoom</Button>
              <Chip label={`${previewZoom}%`} size="small" />
              <Button size="small" variant="outlined" onClick={() => setPreviewZoom((z) => Math.min(200, z + 10))} disabled={previewZoom >= 200}>+ Zoom</Button>
              <Button size="small" onClick={() => setPreviewZoom(100)}>Reset</Button>
            </Stack>
          </Stack>
          <Stack direction="row" alignItems="center" justifyContent="center" spacing={1} sx={{ mb: 1.5 }}>
            <Button size="small" variant="outlined" onClick={() => setPreviewPage((p) => Math.max(1, p - 1))} disabled={previewPage <= 1}>Previous</Button>
            <Typography variant="body2">Page {previewPage} of {uploadResult.page_count}</Typography>
            <Button size="small" variant="outlined" onClick={() => setPreviewPage((p) => Math.min(uploadResult.page_count, p + 1))} disabled={previewPage >= uploadResult.page_count}>Next</Button>
          </Stack>
          <Box sx={{ height: { xs: 520, md: 720 }, width: "100%", border: 1, borderColor: "divider", borderRadius: 1, overflow: "hidden", bgcolor: "#525252" }}>
            <iframe
              title={`PDF preview: ${selectedFile.name}`}
              src={`${pdfPreviewUrl}#page=${previewPage}&zoom=${previewZoom}`}
              style={{ width: "100%", height: "100%", border: 0, background: "#525252" }}
            />
          </Box>
          <Alert severity="info" sx={{ mt: 1.5 }}>
            Preview uses your browser's built-in PDF viewer. Page and zoom controls may behave differently across browsers.
          </Alert>
        </Paper>
      )}


      <Box sx={{ mt: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1.5 }}>PDF workflow</Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
          {[
            { step: "01", title: "Upload", description: "Choose and upload a digital PDF" },
            { step: "02", title: "Analyze", description: "Extract document fields with AI" },
            { step: "03", title: "Review & Edit", description: "Verify and update extracted data" },
            { step: "04", title: "Preview", description: "Review the document" },
          ].map((item, index) => {
            const completed = index === 0 ? !!uploadResult : index === 1 ? !!analysisResult : index === 2 ? editsSaved : false;
            const current = index === 0 ? !uploadResult : index === 1 ? !!uploadResult && !analysisResult : index === 2 ? !!analysisResult && !editsSaved : false;
            return (
              <Paper key={item.step} variant="outlined" sx={{ p: 2, borderRadius: 2, flex: 1 }}>
                <Typography variant="caption" color="primary" fontWeight={700}>{item.step}</Typography>
                <Typography fontWeight={600} sx={{ mt: 0.5 }}>{item.title}</Typography>
                <Typography variant="body2" color="text.secondary">{item.description}</Typography>
                {completed && <Chip size="small" label="Completed" color="success" sx={{ mt: 1 }} />}
                {current && <Chip size="small" label="Current step" color="info" sx={{ mt: 1 }} />}
              </Paper>
            );
          })}
        </Stack>
      </Box>
    </Box>
  );
}
