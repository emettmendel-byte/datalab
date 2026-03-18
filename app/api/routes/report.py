from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.deps import get_session
from app.models import Dataset, ModelRun, Project, ProjectReport, TransformationStep
from app.services.ai_agent import DataScienceAgent


router = APIRouter(prefix="/api", tags=["report"])


@router.post("/models/{model_run_id}/report")
async def generate_report(model_run_id: int, session: Session = Depends(get_session)) -> dict:
    model_run = session.get(ModelRun, model_run_id)
    if not model_run:
        raise HTTPException(status_code=404, detail="Model run not found")

    dataset = session.get(Dataset, model_run.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    project = session.get(Project, model_run.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    steps = list(
        session.exec(
            select(TransformationStep)
            .where(TransformationStep.dataset_id == dataset.id)
            .order_by(TransformationStep.created_at.asc(), TransformationStep.step_index.asc())
        )
    )

    metrics_obj = {}
    if model_run.metrics_json:
        try:
            metrics_obj = json.loads(model_run.metrics_json)
        except Exception:
            metrics_obj = {"raw_metrics_json": model_run.metrics_json}

    config_obj = {}
    if model_run.config_json:
        try:
            config_obj = json.loads(model_run.config_json)
        except Exception:
            config_obj = {"raw_config_json": model_run.config_json}

    schema_obj = {}
    if dataset.schema_json:
        try:
            schema_obj = json.loads(dataset.schema_json)
        except Exception:
            schema_obj = {"raw_schema_json": dataset.schema_json}

    context = {
        "project": {"id": project.id, "name": project.name, "description": project.description},
        "dataset": {
            "id": dataset.id,
            "name": dataset.name,
            "source_type": dataset.source_type,
            "row_count": dataset.row_count,
            "schema": schema_obj,
        },
        "model_run": {
            "id": model_run.id,
            "status": model_run.status,
            "config": config_obj,
            "metrics": metrics_obj,
        },
        "transformation_steps": [
            {
                "tab_name": s.tab_name,
                "step_index": s.step_index,
                "description": s.description,
                "code_snippet": s.code_snippet,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in steps
        ],
    }

    agent = DataScienceAgent()
    try:
        body = await agent.generate_report_markdown(context)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="The AI report generator couldn't produce a report right now. Please try again.",
        )

    report = ProjectReport(project_id=project.id, model_run_id=model_run.id, body=body)
    session.add(report)
    session.commit()
    session.refresh(report)

    return {
        "report_id": report.id,
        "project_id": report.project_id,
        "model_run_id": report.model_run_id,
        "body": report.body,
        "created_at": report.created_at,
    }


@router.get("/projects/{project_id}/reports/latest")
def latest_report(project_id: int, session: Session = Depends(get_session)) -> dict:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    report = session.exec(
        select(ProjectReport)
        .where(ProjectReport.project_id == project_id)
        .order_by(ProjectReport.created_at.desc())
        .limit(1)
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="No report found for this project yet.")

    return {
        "report_id": report.id,
        "project_id": report.project_id,
        "model_run_id": report.model_run_id,
        "body": report.body,
        "created_at": report.created_at,
    }

