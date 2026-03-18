from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.deps import get_session
from app.models import Dataset, ModelRun, Project, ProjectReport
from app.schemas import DatasetRead, ProjectCreate, ProjectRead, ProjectSummary, ProjectUpdate


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectRead)
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)) -> Project:
    project = Project(
        user_id=payload.user_id,
        name=payload.name,
        description=payload.description,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(session: Session = Depends(get_session)) -> list[Project]:
    return list(session.exec(select(Project).order_by(Project.updated_at.desc())))


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, session: Session = Depends(get_session)) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, session: Session = Depends(get_session)) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(project, k, v)
    project.updated_at = datetime.utcnow()

    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.delete("/{project_id}")
def delete_project(project_id: int, session: Session = Depends(get_session)) -> dict:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    session.delete(project)
    session.commit()
    return {"ok": True}


@router.get("/{project_id}/summary", response_model=ProjectSummary)
def project_summary(project_id: int, session: Session = Depends(get_session)) -> ProjectSummary:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    datasets = list(session.exec(select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.created_at.desc())))
    model_runs_count = len(list(session.exec(select(ModelRun.id).where(ModelRun.project_id == project_id))))
    latest_report = session.exec(
        select(ProjectReport).where(ProjectReport.project_id == project_id).order_by(ProjectReport.created_at.desc()).limit(1)
    ).first()

    return ProjectSummary(
        project=ProjectRead.model_validate(project),
        datasets=[DatasetRead.model_validate(d) for d in datasets],
        model_runs_count=model_runs_count,
        latest_report_body=latest_report.body if latest_report else None,
    )

