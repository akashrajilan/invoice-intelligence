import { useRef, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const ACCEPTED_TYPES = ["application/pdf", "image/png", "image/jpeg"];

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function confidenceClass(confidence) {
  if (confidence >= 0.85) return "high";
  if (confidence >= 0.6) return "medium";
  return "low";
}

function FieldEditor({ label, field, onChange }) {
  const confidence = Math.round((field?.confidence || 0) * 100);
  return (
    <label className="field-editor">
      <span>{label}</span>
      <div>
        <input
          value={field?.value ?? ""}
          placeholder="Not detected"
          onChange={(event) => onChange(event.target.value)}
        />
        <small className={confidenceClass(field?.confidence || 0)}>{confidence}%</small>
      </div>
    </label>
  );
}

export default function App() {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [activeView, setActiveView] = useState("upload");
  const [history, setHistory] = useState([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  async function showHistory() {
    setActiveView("history");
    setHistoryLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/invoices?limit=50`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Unable to load history.");
      setHistory(payload.items);
      setHistoryTotal(payload.total);
    } catch (historyError) {
      setError(historyError.message || "Unable to load history.");
    } finally {
      setHistoryLoading(false);
    }
  }

  async function viewInvoice(documentId) {
    setDetailLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/invoices/${documentId}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Unable to load invoice.");
      setSelectedInvoice(payload);
    } catch (detailError) {
      setError(detailError.message || "Unable to load invoice.");
    } finally {
      setDetailLoading(false);
    }
  }

  async function deleteStoredInvoice(documentId) {
    const confirmed = window.confirm("Delete this processed invoice from history? This cannot be undone.");
    if (!confirmed) return;
    try {
      const response = await fetch(`${API_URL}/api/v1/invoices/${documentId}`, { method: "DELETE" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Unable to delete invoice.");
      setSelectedInvoice(null);
      await showHistory();
    } catch (deleteError) {
      setError(deleteError.message || "Unable to delete invoice.");
    }
  }

  function updateInvoiceField(key, value) {
    setResult((current) => ({
      ...current,
      invoice: {
        ...current.invoice,
        [key]: { ...current.invoice[key], value },
      },
    }));
  }

  function chooseFile(candidate) {
    setResult(null);
    setError("");
    if (!candidate) return;
    if (!ACCEPTED_TYPES.includes(candidate.type)) {
      setFile(null);
      setError("Choose a PDF, PNG, JPG, or JPEG invoice.");
      return;
    }
    if (candidate.size > 10 * 1024 * 1024) {
      setFile(null);
      setError("The file must be 10 MB or smaller.");
      return;
    }
    setFile(candidate);
    setStatus("idle");
  }

  async function uploadFile() {
    if (!file) return;
    setStatus("uploading");
    setError("");
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_URL}/api/v1/invoices/upload`, {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Upload failed.");
      setResult(payload);
      setStatus("success");
    } catch (uploadError) {
      setError(uploadError.message || "Unable to connect to the API.");
      setStatus("error");
    }
  }

  return (
    <main className="page-shell">
      <nav className="nav">
        <div className="brand-mark">II</div>
        <div>
          <strong>Invoice Intelligence</strong>
          <span>AI document processing</span>
        </div>
        <div className="nav-actions">
          <button className={activeView === "upload" ? "active" : ""} onClick={() => setActiveView("upload")}>Process</button>
          <button className={activeView === "history" ? "active" : ""} onClick={showHistory}>History</button>
        </div>
      </nav>

      {activeView === "upload" ? (
      <>
      <section className="hero">
        <div className="eyebrow">SMART DOCUMENT AUTOMATION</div>
        <h1>Turn invoices into structured data.</h1>
        <p>
          Upload an invoice or receipt and prepare it for accurate field
          extraction, validation, and export.
        </p>
      </section>

      <section className="workspace">
        <div className="upload-card">
          <div
            className={`drop-zone ${dragging ? "dragging" : ""}`}
            onDragEnter={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              chooseFile(event.dataTransfer.files[0]);
            }}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex="0"
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
            }}
          >
            <div className="upload-icon">↑</div>
            <h2>Upload an invoice</h2>
            <p>Drag and drop a file here, or click to browse.</p>
            <span>PDF, PNG, JPG or JPEG · Maximum 10 MB</span>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              hidden
              onChange={(event) => chooseFile(event.target.files[0])}
            />
          </div>

          {file && (
            <div className="file-row">
              <div className="file-badge">DOC</div>
              <div>
                <strong>{file.name}</strong>
                <span>{formatBytes(file.size)}</span>
              </div>
              <button className="text-button" onClick={() => setFile(null)}>
                Remove
              </button>
            </div>
          )}

          {error && <div className="alert error">{error}</div>}
          {result && (
            <div className="alert success">
              <strong>Document processed</strong>
              <span>{result.message}</span>
              <small>
                {result.page_count} page · {result.extracted_characters} characters · {result.extraction_method.replace("_", " ")}
              </small>
            </div>
          )}

          {result?.duplicate && (
            <div className="alert duplicate-alert">
              <strong>Duplicate document detected</strong>
              <span>This file matches document {result.duplicate_of} and was not saved again.</span>
            </div>
          )}

          {result?.raw_text && (
            <section className="extraction-result">
              <div className="result-heading">
                <div>
                  <span>OCR OUTPUT</span>
                  <h2>Extracted text</h2>
                </div>
                <button
                  className="text-button"
                  onClick={() => navigator.clipboard.writeText(result.raw_text)}
                >
                  Copy text
                </button>
              </div>
              <pre>{result.raw_text}</pre>
            </section>
          )}

          {result?.invoice && (
            <section className="structured-result">
              <div className="result-heading">
                <div>
                  <span>STRUCTURED DATA</span>
                  <h2>Detected invoice fields</h2>
                </div>
                {result.invoice.totals_valid !== null && (
                  <div className={`validation-pill ${result.invoice.totals_valid ? "valid" : "invalid"}`}>
                    {result.invoice.totals_valid ? "Totals match" : "Check totals"}
                  </div>
                )}
              </div>

              <div className="engine-row">
                <span>Field extraction engine</span>
                <strong>{result.invoice.extraction_engine.replaceAll("-", " ")}</strong>
              </div>

              <div className="field-grid">
                {[
                  ["vendor_name", "Vendor"],
                  ["invoice_number", "Invoice number"],
                  ["invoice_date", "Invoice date"],
                  ["due_date", "Due date"],
                  ["currency", "Currency"],
                  ["subtotal", "Subtotal"],
                  ["tax", "Tax"],
                  ["total", "Total"],
                ].map(([key, label]) => (
                  <FieldEditor
                    key={key}
                    label={label}
                    field={result.invoice[key]}
                    onChange={(value) => updateInvoiceField(key, value)}
                  />
                ))}
              </div>

              {result.invoice.line_items.length > 0 && (
                <div className="items-table-wrap">
                  <h3>Line items</h3>
                  <table>
                    <thead><tr><th>Description</th><th>Qty</th><th>Unit price</th><th>Amount</th></tr></thead>
                    <tbody>
                      {result.invoice.line_items.map((item, index) => (
                        <tr key={`${item.description}-${index}`}>
                          <td>{item.description}</td><td>{item.quantity ?? "—"}</td>
                          <td>{item.unit_price ?? "—"}</td><td>{item.amount}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {result.invoice.warnings.length > 0 && (
                <div className="warnings">
                  <strong>Review suggested</strong>
                  {result.invoice.warnings.map((warning) => <p key={warning}>• {warning}</p>)}
                </div>
              )}
            </section>
          )}

          <button
            className="primary-button"
            disabled={!file || status === "uploading"}
            onClick={uploadFile}
          >
            {status === "uploading" ? "Extracting text…" : "Process invoice"}
          </button>
        </div>

        <aside className="feature-panel">
          <h2>Processing pipeline</h2>
          {[
            ["01", "Secure upload", "Validate document type and size."],
            ["02", "OCR extraction", "Read text and document structure."],
            ["03", "Smart validation", "Check totals and uncertain fields."],
            ["04", "Structured export", "Download clean JSON or CSV data."],
          ].map(([number, title, description]) => (
            <div className="feature" key={number}>
              <span>{number}</span>
              <div>
                <strong>{title}</strong>
                <p>{description}</p>
              </div>
            </div>
          ))}
        </aside>
      </section>
      </>
      ) : (
        <section className="history-page">
          <div className="history-header">
            <div>
              <div className="eyebrow">PROCESSING HISTORY</div>
              <h1>Saved invoices</h1>
              <p>{historyTotal} unique document{historyTotal === 1 ? "" : "s"} processed</p>
            </div>
            <button className="secondary-button" onClick={() => setActiveView("upload")}>Process new invoice</button>
          </div>
          {error && <div className="alert error">{error}</div>}
          {historyLoading ? (
            <div className="empty-state">Loading invoice history…</div>
          ) : history.length === 0 ? (
            <div className="empty-state">No invoices have been processed yet.</div>
          ) : (
            <div className="history-list">
              {history.map((item) => (
                <article className="history-card" key={item.document_id}>
                  <div className="history-icon">INV</div>
                  <div className="history-details">
                    <strong>{item.vendor_name || item.filename}</strong>
                    <span>{item.invoice_number || "No invoice number"} · {item.filename}</span>
                  </div>
                  <div className="history-amount">
                    <strong>{item.currency || ""} {item.total ?? "—"}</strong>
                    <span>{new Date(`${item.created_at}Z`).toLocaleString()}</span>
                  </div>
                  <button className="view-button" onClick={() => viewInvoice(item.document_id)}>View</button>
                </article>
              ))}
            </div>
          )}

          {detailLoading && <div className="detail-loading">Loading details…</div>}
          {selectedInvoice && (
            <div className="detail-overlay" onClick={() => setSelectedInvoice(null)}>
              <section className="detail-panel" onClick={(event) => event.stopPropagation()}>
                <div className="detail-topbar">
                  <div>
                    <span>INVOICE DETAILS</span>
                    <h2>{selectedInvoice.invoice.vendor_name.value || selectedInvoice.filename}</h2>
                  </div>
                  <button className="close-button" onClick={() => setSelectedInvoice(null)}>×</button>
                </div>
                <div className="engine-row detail-engine">
                  <span>Field extraction engine</span>
                  <strong>{selectedInvoice.invoice.extraction_engine.replaceAll("-", " ")}</strong>
                </div>
                <div className="detail-grid">
                  {[
                    ["Invoice", selectedInvoice.invoice.invoice_number.value],
                    ["Invoice date", selectedInvoice.invoice.invoice_date.value],
                    ["Due date", selectedInvoice.invoice.due_date.value],
                    ["Subtotal", selectedInvoice.invoice.subtotal.value],
                    ["Tax", selectedInvoice.invoice.tax.value],
                    ["Total", selectedInvoice.invoice.total.value],
                  ].map(([label, value]) => (
                    <div key={label}><span>{label}</span><strong>{value ?? "Not detected"}</strong></div>
                  ))}
                </div>
                {selectedInvoice.invoice.line_items.length > 0 && (
                  <div className="items-table-wrap detail-items">
                    <h3>Line items</h3>
                    <table>
                      <thead><tr><th>Description</th><th>Qty</th><th>Unit price</th><th>Amount</th></tr></thead>
                      <tbody>{selectedInvoice.invoice.line_items.map((item, index) => (
                        <tr key={`${item.description}-${index}`}><td>{item.description}</td><td>{item.quantity ?? "—"}</td><td>{item.unit_price ?? "—"}</td><td>{item.amount}</td></tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
                <div className="detail-actions">
                  <a href={`${API_URL}/api/v1/invoices/${selectedInvoice.document_id}/export?format=json`}>Download JSON</a>
                  <a href={`${API_URL}/api/v1/invoices/${selectedInvoice.document_id}/export?format=csv`}>Download CSV</a>
                  <button onClick={() => deleteStoredInvoice(selectedInvoice.document_id)}>Delete</button>
                </div>
              </section>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
