from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    name: str
    description: str | None = None
    lifecycle_state: str = Field(default="new", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class Dataset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True, foreign_key="project.id")
    name: str
    source_type: str = Field(index=True)  # "upload" | "scrape" | "api"
    s3_key: str
    schema_json: str | None = None
    row_count: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class TransformationStep(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_id: int = Field(index=True, foreign_key="dataset.id")
    tab_name: str = Field(index=True)
    step_index: int = Field(index=True)
    code_snippet: str
    description: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class ModelRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True, foreign_key="project.id")
    dataset_id: int = Field(index=True, foreign_key="dataset.id")
    config_json: str | None = None
    metrics_json: str | None = None
    s3_model_key: str | None = None
    status: str = Field(default="created", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class AgentPrompt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True, foreign_key="project.id")
    tab_name: str = Field(index=True)
    role: str = Field(index=True)  # "system" | "user" | "assistant"
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class ProjectReport(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True, foreign_key="project.id")
    model_run_id: int | None = Field(default=None, foreign_key="modelrun.id")
    body: str
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

