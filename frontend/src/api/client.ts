import type {
  ChartConfig,
  Dataset,
  ExploreInsight,
  ModelRunSummary,
  Plan,
  PlanStep,
  Project,
  ProjectReport,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

function extractErrorMessage(raw: string, fallback: string): string {
  try {
    const parsed = JSON.parse(raw) as { detail?: string };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    // ignore
  }
  return raw || fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(extractErrorMessage(text, `Request failed with status ${resp.status}`));
  }
  return (await resp.json()) as T;
}

export async function listProjects() {
  return request<Project[]>("/projects");
}

export async function createProject(args: { name: string; description?: string; user_id?: number }) {
  return request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify({
      user_id: args.user_id ?? 1,
      name: args.name,
      description: args.description ?? null,
    }),
  });
}

export async function listDatasets(projectId: number) {
  return request<Dataset[]>(`/projects/${projectId}/datasets`);
}

export async function previewDataset(datasetId: number, page = 1, pageSize = 100) {
  return request<{
    rows: Record<string, unknown>[];
    columns: Array<{ name: string; dtype: string }>;
    schema?: unknown;
  }>(`/datasets/${datasetId}/preview?page=${page}&page_size=${pageSize}`);
}

export async function uploadDataset(projectId: number, args: { file: File; name: string; description?: string }) {
  const formData = new FormData();
  formData.append("file", args.file);
  formData.append("name", args.name);
  if (args.description) formData.append("description", args.description);

  const resp = await fetch(`${API_BASE}/projects/${projectId}/datasets/upload`, {
    method: "POST",
    body: formData,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(extractErrorMessage(text, "Upload failed."));
  }
  return resp.json() as Promise<{
    dataset: Dataset;
    rows: Record<string, unknown>[];
    columns: Array<{ name: string; dtype: string }>;
  }>;
}

export async function askAgentPlan(projectId: number, goal: string, datasetId?: number | null) {
  return request<Plan>(`/projects/${projectId}/agent/plan`, {
    method: "POST",
    body: JSON.stringify({ goal, dataset_id: datasetId ?? null }),
  });
}

export async function runClean(
  datasetId: number,
  steps: Array<{ operation_type: string; parameters: object; description: string; generated_code?: string | null }>,
  instruction?: string,
) {
  return request<{
    rows: Record<string, unknown>[];
    schema_json: string;
    execution_source?: string;
    row_count_before?: number | null;
    row_count_after?: number | null;
    before_preview?: { page: number; page_size: number; columns: Array<{ name: string; dtype: string }>; rows: Record<string, unknown>[] };
    before_window_rows?: Record<string, unknown>[];
    after_preview?: { page: number; page_size: number; columns: Array<{ name: string; dtype: string }>; rows: Record<string, unknown>[] };
    applied_steps?: Array<{ operation_type: string; parameters: Record<string, unknown>; description: string; generated_code?: string | null }>;
    transformation_steps: Array<{ id: number; description?: string | null; code_snippet: string }>;
  }>(`/datasets/${datasetId}/clean`, {
    method: "POST",
    body: JSON.stringify({ steps, instruction: instruction ?? null }),
  });
}

export async function suggestCleanSteps(datasetId: number, instruction?: string) {
  return request<{
    source: string;
    instruction: string;
    steps: Array<{ operation_type: string; parameters: Record<string, unknown>; description: string; generated_code?: string | null }>;
  }>(`/datasets/${datasetId}/clean/suggest`, {
    method: "POST",
    body: JSON.stringify({ instruction: instruction ?? null }),
  });
}

export async function diagnoseCleanMessiness(datasetId: number, instruction?: string) {
  return request<{
    source: string;
    instruction: string;
    message: string;
  }>(`/datasets/${datasetId}/clean/diagnose`, {
    method: "POST",
    body: JSON.stringify({ instruction: instruction ?? null }),
  });
}

export async function getExploreInsights(datasetId: number) {
  return request<ExploreInsight[]>(`/datasets/${datasetId}/explore`);
}

export async function getExploreSuggestedQuestions(datasetId: number) {
  return request<{ source: string; questions: string[] }>(`/datasets/${datasetId}/explore/suggested-questions`);
}

export async function askExploreQuestion(datasetId: number, question: string) {
  return request<{ source: string; question: string; answer: string }>(`/datasets/${datasetId}/explore/chat`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export async function explainExploreStep(datasetId: number, step: PlanStep) {
  return request<{ explanation: string }>(`/datasets/${datasetId}/explore/explain`, {
    method: "POST",
    body: JSON.stringify({ step }),
  });
}

export async function suggestCharts(datasetId: number, question: string) {
  return request<ChartConfig[]>(`/datasets/${datasetId}/charts/suggest`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export async function fetchChartData(datasetId: number, config: ChartConfig) {
  return request<{ plotly: { type: string; x?: unknown[]; y?: unknown[]; color?: unknown[] } }>(
    `/datasets/${datasetId}/charts/data`,
    {
      method: "POST",
      body: JSON.stringify({ config }),
    },
  );
}

export async function trainModel(datasetId: number, goal: string) {
  return request<ModelRunSummary>(`/datasets/${datasetId}/models/train`, {
    method: "POST",
    body: JSON.stringify({ goal }),
  });
}

export async function predictModel(modelRunId: number, row: Record<string, unknown>) {
  return request<{ prediction: unknown; probabilities?: Record<string, number> | number[] }>(`/models/${modelRunId}/predict`, {
    method: "POST",
    body: JSON.stringify({ row }),
  });
}

export async function generateReport(modelRunId: number) {
  return request<ProjectReport>(`/models/${modelRunId}/report`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function latestReport(projectId: number) {
  return request<ProjectReport>(`/projects/${projectId}/reports/latest`);
}
