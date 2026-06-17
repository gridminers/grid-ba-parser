"use client";

import { useEffect, useMemo, useState } from "react";
import {
  API_BASE,
  DocumentDraft,
  DocumentRecord,
  JobStatus,
  VlmModelInfo,
  VlmModelsResponse,
  apiJson,
  artifactUrl
} from "../lib/api";

type DocumentsResponse = { documents: DocumentRecord[] };
type UploadResponse = { documents: DocumentRecord[] };
type ValidateResponse = { valid: boolean; errors: string[]; warnings: string[] };
type SyncResponse = { status: string; message: string; chunks: number; embeddings: number };

function statusClass(status: string) {
  return `status ${status}`;
}

function downloadText(filename: string, text: string, mime: string) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function fieldsToCsv(draft: DocumentDraft) {
  const header = [
    "label",
    "value_raw",
    "value_normalized",
    "type",
    "section",
    "page",
    "confidence",
    "source",
    "evidence"
  ];
  const rows = draft.fields.map((field) =>
    header
      .map((key) => {
        const value = String((field as unknown as Record<string, unknown>)[key] ?? "");
        return `"${value.replaceAll('"', '""')}"`;
      })
      .join(",")
  );
  return [header.join(","), ...rows].join("\n");
}

export default function Home() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [draft, setDraft] = useState<DocumentDraft | null>(null);
  const [rawJson, setRawJson] = useState("");
  const [job, setJob] = useState<JobStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [rerunPage, setRerunPage] = useState(1);
  const [vlmProvider, setVlmProvider] = useState("ollama");
  const [vlmModel, setVlmModel] = useState("");
  const [vlmModels, setVlmModels] = useState<VlmModelInfo[]>([]);
  const [vlmMessage, setVlmMessage] = useState("");

  const selectedDocument = useMemo(
    () => documents.find((item) => item.id === selectedId) || null,
    [documents, selectedId]
  );

  async function refreshDocuments() {
    const data = await apiJson<DocumentsResponse>("/documents");
    setDocuments(data.documents);
    if (!selectedId && data.documents[0]) {
      setSelectedId(data.documents[0].id);
    }
  }

  async function loadDraft(id: string) {
    const data = await apiJson<DocumentDraft>(`/documents/${id}/draft`);
    setDraft(data);
    setRawJson(JSON.stringify(data, null, 2));
  }

  async function refreshVlmModels(provider = vlmProvider) {
    setError("");
    try {
      const response = await apiJson<VlmModelsResponse>(
        `/vlm/models?provider=${encodeURIComponent(provider)}`
      );
      const likelyVision = response.models.filter((model) => model.vision_likely);
      const modelsToShow = likelyVision.length ? likelyVision : response.models;
      setVlmModels(modelsToShow);
      setVlmMessage(
        likelyVision.length
          ? `${response.message}; showing ${likelyVision.length} likely vision model(s)`
          : `${response.message}; no vision-tagged match, showing all returned models`
      );
      if (!modelsToShow.some((model) => model.id === vlmModel)) {
        setVlmModel(modelsToShow[0]?.id || response.configured_model || "");
      }
    } catch (exc) {
      setVlmModels([]);
      setVlmMessage(String(exc));
    }
  }

  useEffect(() => {
    refreshDocuments().catch((exc) => setError(String(exc)));
  }, []);

  useEffect(() => {
    refreshVlmModels(vlmProvider).catch((exc) => setError(String(exc)));
  }, [vlmProvider]);

  useEffect(() => {
    if (selectedId) {
      loadDraft(selectedId).catch((exc) => setError(String(exc)));
    }
  }, [selectedId]);

  useEffect(() => {
    if (!job || job.state === "completed" || job.state === "failed") return;
    const timer = window.setInterval(async () => {
      try {
        const nextJob = await apiJson<JobStatus>(`/jobs/${job.id}`);
        setJob(nextJob);
        if (nextJob.state === "completed") {
          await refreshDocuments();
          await loadDraft(nextJob.document_id);
        }
      } catch (exc) {
        setError(String(exc));
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job]);

  async function handleUpload(formData: FormData) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(`${API_BASE}/documents/upload`, {
        method: "POST",
        body: formData
      });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as UploadResponse;
      setDocuments(data.documents);
      if (data.documents[0]) setSelectedId(data.documents[0].id);
      await refreshDocuments();
      setMessage(`Uploaded ${data.documents.length} document(s)`);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  async function startParse() {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (vlmProvider) params.set("vlm_provider", vlmProvider);
      if (vlmModel) params.set("vlm_model", vlmModel);
      const nextJob = await apiJson<JobStatus>(
        `/documents/${selectedId}/parse?${params.toString()}`,
        { method: "POST" }
      );
      setJob(nextJob);
      setMessage("Parse queued");
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  async function rerunSelectedPage() {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("page", String(rerunPage));
      if (vlmProvider) params.set("vlm_provider", vlmProvider);
      if (vlmModel) params.set("vlm_model", vlmModel);
      const nextJob = await apiJson<JobStatus>(
        `/documents/${selectedId}/rerun-page?${params.toString()}`,
        { method: "POST" }
      );
      setJob(nextJob);
      setMessage(`Page ${rerunPage} rerun queued`);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  function parseEditorJson(): DocumentDraft | null {
    try {
      const parsed = JSON.parse(rawJson) as DocumentDraft;
      setDraft(parsed);
      setError("");
      return parsed;
    } catch (exc) {
      setError(`Invalid JSON: ${String(exc)}`);
      return null;
    }
  }

  async function saveDraft() {
    if (!selectedId) return;
    const parsed = parseEditorJson();
    if (!parsed) return;
    setBusy(true);
    try {
      const saved = await apiJson<DocumentDraft>(`/documents/${selectedId}/draft`, {
        method: "PATCH",
        body: JSON.stringify(parsed)
      });
      setDraft(saved);
      setRawJson(JSON.stringify(saved, null, 2));
      setMessage("Draft saved");
      await refreshDocuments();
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  async function validateDraft() {
    if (!selectedId) return;
    const parsed = parseEditorJson();
    if (!parsed) return;
    try {
      const result = await apiJson<ValidateResponse>(`/documents/${selectedId}/validate`, {
        method: "POST",
        body: JSON.stringify(parsed)
      });
      setMessage(
        result.valid
          ? `Valid. Warnings: ${result.warnings.length}`
          : `Invalid: ${result.errors.join("; ")}`
      );
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function syncDraft() {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      const result = await apiJson<SyncResponse>(`/documents/${selectedId}/sync`, {
        method: "POST"
      });
      setMessage(
        `${result.status}: ${result.message}. chunks=${result.chunks}, embeddings=${result.embeddings}`
      );
      await refreshDocuments();
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  function updateField(index: number, key: "label" | "value_raw" | "value_normalized", value: string) {
    if (!draft) return;
    const next: DocumentDraft = {
      ...draft,
      fields: draft.fields.map((field, fieldIndex) =>
        fieldIndex === index ? { ...field, [key]: value } : field
      )
    };
    setDraft(next);
    setRawJson(JSON.stringify(next, null, 2));
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <h1 className="title">Grid BA Parser</h1>
        <div className="subtle">Technical extraction console</div>

        <div className="panel" style={{ marginTop: 14 }}>
          <div className="panel-header">
            <strong>Upload PDFs</strong>
          </div>
          <div className="panel-body">
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const form = event.currentTarget;
                const data = new FormData(form);
                handleUpload(data);
                form.reset();
              }}
            >
              <input name="files" type="file" accept="application/pdf" multiple />
              <div className="toolbar">
                <button className="primary" disabled={busy} type="submit">
                  Upload
                </button>
                <button type="button" onClick={refreshDocuments}>
                  Refresh
                </button>
              </div>
            </form>
          </div>
        </div>

        <div className="doc-list">
          {documents.map((doc) => (
            <button
              className={`doc-button ${doc.id === selectedId ? "active" : ""}`}
              key={doc.id}
              onClick={() => setSelectedId(doc.id)}
            >
              <strong>{doc.filename}</strong>
              <br />
              <span className={statusClass(doc.status)}>{doc.status}</span>{" "}
              <span className="subtle">{doc.page_count} pages</span>
              <br />
              <span className="subtle">{doc.sha256.slice(0, 12)}</span>
            </button>
          ))}
          {!documents.length && <div className="subtle">No documents uploaded yet.</div>}
        </div>
      </aside>

      <section className="main">
        {error && <div className="message error">{error}</div>}
        {message && <div className="message">{message}</div>}

        <div className="panel">
          <div className="panel-header">
            <div>
              <strong>{selectedDocument?.filename || "No document selected"}</strong>
              {selectedDocument && (
                <div className="subtle">
                  {selectedDocument.id} | <span className={statusClass(selectedDocument.status)}>{selectedDocument.status}</span>
                </div>
              )}
            </div>
            <div className="toolbar">
              <select
                aria-label="VLM provider"
                value={vlmProvider}
                onChange={(event) => {
                  setVlmProvider(event.target.value);
                  setVlmModel("");
                }}
              >
                <option value="ollama">Ollama local</option>
                <option value="local_vllm">vLLM local</option>
                <option value="openai">OpenAI hosted</option>
              </select>
              <select
                aria-label="Vision model"
                style={{ minWidth: 230 }}
                value={vlmModel}
                onChange={(event) => setVlmModel(event.target.value)}
              >
                {vlmModels.map((model) => (
                  <option key={`${model.provider}-${model.id}`} value={model.id}>
                    {model.id}
                    {model.installed ? "" : " (configured)"}
                  </option>
                ))}
                {!vlmModels.length && vlmModel && <option value={vlmModel}>{vlmModel}</option>}
                {!vlmModels.length && !vlmModel && <option value="">No model found</option>}
              </select>
              <button type="button" onClick={() => refreshVlmModels()}>
                Refresh models
              </button>
              <button className="primary" disabled={!selectedId || busy} onClick={startParse}>
                Parse
              </button>
              <button disabled={!selectedId || busy} onClick={startParse}>
                Re-run document
              </button>
              <input
                min={1}
                style={{ width: 72 }}
                type="number"
                value={rerunPage}
                onChange={(event) => setRerunPage(Number(event.target.value))}
              />
              <button disabled={!selectedId || busy} onClick={rerunSelectedPage}>
                Re-run page with VLM
              </button>
              <button disabled={!draft} onClick={validateDraft}>
                Validate JSON
              </button>
              <button disabled={!draft || busy} onClick={saveDraft}>
                Save draft
              </button>
              <button disabled={!draft || busy} onClick={syncDraft}>
                Sync to Supabase
              </button>
            </div>
          </div>
          <div className="panel-body">
            <div className="subtle">
              VLM: {vlmProvider}
              {vlmModel ? ` / ${vlmModel}` : ""}. {vlmMessage}
            </div>
            {job && (
              <>
                <div>
                  Job <code>{job.id}</code>: <span className={statusClass(job.state)}>{job.state}</span>{" "}
                  {job.message} ({Math.round(job.progress * 100)}%)
                </div>
                <div className="log">{[...job.logs, job.error || ""].filter(Boolean).join("\n")}</div>
              </>
            )}
          </div>
        </div>

        <div className="grid-two">
          <div className="panel">
            <div className="panel-header">
              <strong>Raw Draft JSON</strong>
              <div className="toolbar">
                <button
                  disabled={!draft}
                  onClick={() => draft && downloadText(`${draft.document_id}.json`, rawJson, "application/json")}
                >
                  Export JSON
                </button>
                <button
                  disabled={!draft}
                  onClick={() => draft && downloadText(`${draft.document_id}.csv`, fieldsToCsv(draft), "text/csv")}
                >
                  Export CSV
                </button>
              </div>
            </div>
            <div className="panel-body">
              <textarea
                className="json-editor"
                spellCheck={false}
                value={rawJson}
                onChange={(event) => setRawJson(event.target.value)}
              />
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <strong>Key-Value Fields</strong>
              <span className="subtle">{draft?.fields.length || 0} fields</span>
            </div>
            <div className="panel-body" style={{ overflow: "auto", maxHeight: 520 }}>
              <table>
                <thead>
                  <tr>
                    <th>Label</th>
                    <th>Raw</th>
                    <th>Normalized</th>
                    <th>Page</th>
                    <th>Conf</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {draft?.fields.map((field, index) => (
                    <tr key={`${field.label}-${index}`}>
                      <td>
                        <input
                          value={field.label}
                          onChange={(event) => updateField(index, "label", event.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          value={field.value_raw || ""}
                          onChange={(event) => updateField(index, "value_raw", event.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          value={field.value_normalized || ""}
                          onChange={(event) => updateField(index, "value_normalized", event.target.value)}
                        />
                      </td>
                      <td>{field.page}</td>
                      <td>{field.confidence.toFixed(2)}</td>
                      <td>{field.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <strong>Page Debug Artifacts</strong>
            <span className="subtle">Routes, confidence, page images, OCR text paths</span>
          </div>
          <div className="panel-body page-grid">
            {draft?.pages.map((page) => (
              <div className="page-card" key={page.page}>
                <strong>Page {page.page}</strong> <span className={statusClass(page.route)}>{page.route}</span>
                <div className="subtle">
                  quality {page.quality_score.toFixed(2)}
                  {page.ocr_confidence != null ? ` | OCR ${page.ocr_confidence.toFixed(2)}` : ""}
                </div>
                {artifactUrl(page.image_url) && (
                  <a href={artifactUrl(page.image_url) || "#"} target="_blank">
                    <img alt={`Page ${page.page}`} src={artifactUrl(page.image_url) || ""} />
                  </a>
                )}
                <div className="subtle">
                  OCR text: <code>{page.text_path || "n/a"}</code>
                </div>
                <div className="subtle">
                  VLM: <code>{page.vlm_response_path || "n/a"}</code>
                </div>
                {page.warnings.map((warning) => (
                  <div className="subtle" key={`${warning.code}-${warning.message}`}>
                    {warning.code}: {warning.message}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
