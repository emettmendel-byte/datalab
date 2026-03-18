from __future__ import annotations

from datetime import datetime

from enum import Enum

from pydantic import BaseModel
from pydantic import ConfigDict

AllowedPlanTab = str


class ProjectCreate(BaseModel):
    user_id: int
    name: str
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    lifecycle_state: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    description: str | None
    lifecycle_state: str
    created_at: datetime
    updated_at: datetime


class DatasetCreate(BaseModel):
    name: str
    source_type: str
    s3_key: str
    schema_json: str | None = None
    row_count: int | None = None


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    source_type: str
    s3_key: str
    schema_json: str | None
    row_count: int | None
    created_at: datetime


class AgentPromptCreate(BaseModel):
    tab_name: str
    role: str
    content: str


class AgentPromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    tab_name: str
    role: str
    content: str
    created_at: datetime


class ProjectSummary(BaseModel):
    project: ProjectRead
    datasets: list[DatasetRead]
    model_runs_count: int
    latest_report_body: str | None


class PlanStep(BaseModel):
    tab: AllowedPlanTab  # "Question" | "Data" | "Clean" | "Explore" | "Visualize" | "Model" | "Report"
    operation_type: str
    short_title: str
    user_friendly_explanation: str
    python_pandas_code: str | None = None
    sklearn_code: str | None = None
    narrative_instructions: str | None = None


class Plan(BaseModel):
    steps: list[PlanStep]


class AgentPlanRequest(BaseModel):
    dataset_id: int | None = None
    goal: str


class CleaningOperationType(str, Enum):
    DROP_COLUMNS = "DROP_COLUMNS"
    DROP_ROWS_WITH_MISSING = "DROP_ROWS_WITH_MISSING"
    FILL_MISSING = "FILL_MISSING"
    CAST_TYPE = "CAST_TYPE"
    FILTER_ROWS = "FILTER_ROWS"
    DEDUP_ROWS = "DEDUP_ROWS"
    STANDARDIZE_CATEGORIES = "STANDARDIZE_CATEGORIES"
    PARSE_DATES = "PARSE_DATES"


class CleaningStep(BaseModel):
    operation_type: CleaningOperationType
    parameters: dict = {}
    description: str
    generated_code: str | None = None


class CleanRequest(BaseModel):
    steps: list[CleaningStep]
    instruction: str | None = None


class TransformationStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    tab_name: str
    step_index: int
    code_snippet: str
    description: str | None
    created_at: datetime


class ChartConfig(BaseModel):
    id: str
    chart_type: str  # "histogram" | "scatter" | "bar" | "line"
    x: str | None = None
    y: str | None = None
    color: str | None = None
    aggregation: str | None = None  # e.g. "count" | "mean" | "sum"
    filters: list[dict] | None = None  # list of {column, op, value}
    description: str | None = None


class ExploreInsight(BaseModel):
    id: str
    type: str  # "summary_stats" | "correlation" | "distribution"
    title: str
    description: str
    chart_suggestion: ChartConfig | None = None


class ExploreExplainRequest(BaseModel):
    step: PlanStep


class ChartSuggestRequest(BaseModel):
    question: str


class ChartDataRequest(BaseModel):
    config: ChartConfig


class ModelTrainRequest(BaseModel):
    goal: str


class ModelPredictRequest(BaseModel):
    row: dict


class AgentRunRequest(BaseModel):
    dataset_id: int
    goal: str


class CleanSuggestRequest(BaseModel):
    instruction: str | None = None


class ExploreChatRequest(BaseModel):
    question: str

