import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import MainLayout from "./layouts/MainLayout";

import Dashboard from "./pages/Dashboard";
import Templates from "./pages/Templates";
import TemplateDesigner from "./pages/TemplateDesigner";
import MappingWorkbench from "./pages/MappingWorkbench";
import DocumentGeneration from "./pages/DocumentGeneration";
import BindingReview from "./pages/BindingReview";
import Upload from "./pages/Upload";
import DocumentWorkspace from "./pages/DocumentWorkspace";
import PDFSignatureUpload from "./pages/PDFSignatureUpload";
import PDFDocumentWorkspace from "./pages/PDFDocumentWorkspace";

function SettingsPlaceholder() {
  return (
    <div style={{ padding: "24px" }}>
      <h1>Settings</h1>
      <p>DocQ settings will be available here.</p>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          {/* Dashboard */}
          <Route index element={<Dashboard />} />

          {/* =========================================================
              DOCUMENTS
              ========================================================= */}

          {/* All documents */}
          <Route path="documents" element={<Templates />} />

          {/* Document filters - temporary reuse of Templates page */}
          <Route path="documents/dynamic" element={<Templates />} />
          <Route path="documents/static" element={<Templates />} />
          <Route path="documents/review" element={<Templates />} />

          {/* Individual document workspace */}
          <Route path="documents/:id" element={<DocumentWorkspace />} />

          {/* =========================================================
              DOCUMENT WORKFLOW
              These routes are temporary workflow routes.
              Later they will become steps inside the workspace.
              ========================================================= */}

          <Route path="documents/:id/designer" element={<TemplateDesigner />} />

          <Route path="documents/:id/mapping" element={<MappingWorkbench />} />

          <Route path="documents/:id/bindings" element={<BindingReview />} />

          <Route
            path="documents/:id/generate"
            element={<DocumentGeneration />}
          />

          {/* =========================================================
              UPLOAD
              ========================================================= */}

          <Route path="upload" element={<Upload />} />

          {/* Independent PDF Signature Marker module */}
          <Route path="pdf-upload" element={<PDFSignatureUpload />} />

          {/* Independent Digital PDF Documents workspace */}
          <Route path="pdf-documents" element={<PDFDocumentWorkspace />} />

          {/* =========================================================
              SETTINGS
              ========================================================= */}

          <Route path="settings" element={<SettingsPlaceholder />} />

          {/* =========================================================
              LEGACY ROUTES
              Keep these temporarily so existing links don't break.
              ========================================================= */}

          <Route
            path="templates"
            element={<Navigate to="/documents" replace />}
          />

          <Route
            path="templates/onboarding"
            element={<Navigate to="/upload" replace />}
          />

          <Route
            path="templates/:id"
            element={<Navigate to="/documents" replace />}
          />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
