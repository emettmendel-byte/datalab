from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.deps import get_session
from app.models import AgentPrompt, Project
from app.schemas import AgentPromptCreate, AgentPromptRead


router = APIRouter(prefix="/api/projects/{project_id}/prompts", tags=["prompts"])


@router.get("", response_model=list[AgentPromptRead])
def list_prompts(project_id: int, tab_name: str | None = None, session: Session = Depends(get_session)) -> list[AgentPrompt]:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    stmt = select(AgentPrompt).where(AgentPrompt.project_id == project_id)
    if tab_name:
        stmt = stmt.where(AgentPrompt.tab_name == tab_name)
    stmt = stmt.order_by(AgentPrompt.created_at.desc())
    return list(session.exec(stmt))


@router.post("", response_model=AgentPromptRead)
def create_prompt(project_id: int, payload: AgentPromptCreate, session: Session = Depends(get_session)) -> AgentPrompt:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    prompt = AgentPrompt(
        project_id=project_id,
        tab_name=payload.tab_name,
        role=payload.role,
        content=payload.content,
    )
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return prompt

