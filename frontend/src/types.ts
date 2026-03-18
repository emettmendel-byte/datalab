export type LifecycleTab =
  | "Question"
  | "Data"
  | "Clean"
  | "Explore"
  | "Visualize"
  | "Model"
  | "Report";

export interface Project {
  id: number;
  user_id: number;
  name: string;
  description?: string | null;
}

export interface Dataset {
  id: number;
  project_id: number;
  name: string;
  source_type: string;
  s3_key: string;
  schema_json?: string | null;
  row_count?: number | null;
}

export interface PlanStep {
  tab: LifecycleTab;
  operation_type: string;
  short_title: string;
  user_friendly_explanation: string;
  python_pandas_code?: string | null;
  sklearn_code?: string | null;
  narrative_instructions?: string | null;
}

export interface Plan {
  steps: PlanStep[];
}

export interface ChartConfig {
  id: string;
  chart_type: "histogram" | "scatter" | "bar" | "line" | string;
  x?: string | null;
  y?: string | null;
  color?: string | null;
  aggregation?: string | null;
  filters?: Array<{ column: string; op: string; value: unknown }> | null;
  description?: string | null;
}

export interface ExploreInsight {
  id: string;
  type: "summary_stats" | "correlation" | "distribution" | string;
  title: string;
  description: string;
  chart_suggestion?: ChartConfig | null;
}

export interface ModelRunSummary {
  model_run_id: number;
  config_json: string;
  metrics_json: string;
}

export interface ProjectReport {
  report_id: number;
  project_id: number;
  model_run_id?: number | null;
  body: string;
  created_at: string;
}
