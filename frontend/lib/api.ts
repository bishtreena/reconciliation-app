import axios from "axios";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const client = axios.create({ baseURL: BASE_URL });

// ── Types mirroring backend Pydantic schemas ──────────────────────────────

export interface GapBreakdown {
  gap_type: string;
  count: number;
  total_amount: number;
}

export interface ReconSummary {
  run_id: number;
  created_at: string;
  status: string;
  total_platform_txns: number;
  total_bank_settlements: number;
  platform_total: number;
  bank_total: number;
  total_gap_amount: number;
  rounding_drift_total: number;
  total_gaps: number;
  gap_breakdown: GapBreakdown[];
  narrative: string | null;
}

export interface GapResultOut {
  id: number;
  run_id: number;
  gap_type: string;
  amount: number | null;
  source_row_json: Record<string, unknown> | null;
  classification_confidence: number | null;
  llm_reasoning: string | null;
}

export interface UploadResponse {
  run_id: number;
}

export interface ReconcileResponse {
  result_id: number;
  summary: ReconSummary;
}

export interface ResultsResponse {
  summary: ReconSummary;
  gaps: Record<string, GapResultOut[]>;
}

export interface SampleDataResponse {
  platform_csv: string;
  bank_csv: string;
}

// ── Fetchers ──────────────────────────────────────────────────────────────

/**
 * POST /upload
 * Upload platform and bank CSV files and receive a run_id.
 */
export async function uploadCSVs(
  platformFile: File,
  bankFile: File
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("platform", platformFile);
  form.append("bank", bankFile);
  const { data } = await client.post<UploadResponse>("/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

/**
 * POST /reconcile/{runId}
 * Trigger reconciliation for an uploaded run. Returns the full summary.
 */
export async function reconcileRun(runId: number): Promise<ReconcileResponse> {
  const { data } = await client.post<ReconcileResponse>(
    `/reconcile/${runId}`
  );
  return data;
}

/**
 * GET /results/{runId}
 * Fetch the reconciliation summary and gap details for a completed run.
 */
export async function getResults(runId: number): Promise<ResultsResponse> {
  const { data } = await client.get<ResultsResponse>(`/results/${runId}`);
  return data;
}

/**
 * GET /sample-data
 * Fetch the pre-generated sample CSV strings (useful for demo uploads).
 */
export async function getSampleData(): Promise<SampleDataResponse> {
  const { data } = await client.get<SampleDataResponse>("/sample-data");
  return data;
}