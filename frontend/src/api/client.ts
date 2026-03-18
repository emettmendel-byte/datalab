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
    throw new Error(text || `Request failed with status ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export async function listProjects() {
  return request<Project[]>("/projects");
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
    throw new Error(await resp.text());
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

export async function runClean(datasetId: number, steps: Array<{ operation_type: string; parameters: object; description: string; generated_code?: string | null }>) {
  return request<{
    rows: Record<string, unknown>[];
    schema_json: string;
    transformation_steps: Array<{ id: number; description?: string | null; code_snippet: string }>;
  }>(`/datasets/${datasetId}/clean`, {
    method: "POST",
    body: JSON.stringify({ steps }),
  });
}

export async function getExploreInsights(datasetId: number) {
  return request<ExploreInsight[]>(`/datasets/${datasetId}/explore`);
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
