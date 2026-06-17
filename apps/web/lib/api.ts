export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export type FieldSource = "embedded_text" | "ocr" | "heuristic" | "vlm" | "reviewer";
export type JobState = "queued" | "running" | "completed" | "failed";
export type DocumentStatus = "uploaded" | "parsing" | "draft" | "synced" | "failed";

export type WarningItem = {
  code: string;
  message: string;
  page?: number | null;
  severity: "info" | "warning" | "error";
};

export type ExtractedField = {
  label: string;
  value_raw?: string | null;
  value_normalized?: string | null;
  type: string;
  section?: string | null;
  page: number;
  confidence: number;
  bbox?: number[] | null;
  evidence?: string | null;
  source: FieldSource;
};

export type ExtractedTable = {
  title?: string | null;
  page: number;
  rows: Record<string, unknown>[];
  confidence: number;
  source: FieldSource;
};

export type PageArtifact = {
  page: number;
  image_path?: string | null;
  image_url?: string | null;
  text_path?: string | null;
  vlm_response_path?: string | null;
  route: string;
  quality_score: number;
  ocr_confidence?: number | null;
  warnings: WarningItem[];
};

export type DocumentDraft = {
  document_id: string;
  language: string;
  fields: ExtractedField[];
  tables: ExtractedTable[];
  pages: PageArtifact[];
  warnings: WarningItem[];
  raw_text: string;
  updated_at: string;
};

export type DocumentRecord = {
  id: string;
  filename: string;
  sha256: string;
  status: DocumentStatus;
  source_path: string;
  draft_path?: string | null;
  page_count: number;
  created_at: string;
  updated_at: string;
  warnings: WarningItem[];
};

export type JobStatus = {
  id: string;
  document_id: string;
  state: JobState;
  message: string;
  progress: number;
  logs: string[];
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
};

export type MockDbExportResponse = {
  status: "exported" | "skipped" | "failed";
  message: string;
  document_id: string;
  export_path?: string | null;
  fields: number;
};

export type VlmModelInfo = {
  id: string;
  provider: string;
  installed: boolean;
  vision_likely: boolean;
  details: Record<string, unknown>;
};

export type VlmModelsResponse = {
  provider: string;
  configured_model?: string | null;
  models: VlmModelInfo[];
  message: string;
};

export type ArtifactTextResponse = {
  path: string;
  text: string;
};

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as T;
}

export function artifactUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}
