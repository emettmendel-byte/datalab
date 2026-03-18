from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.deps import get_session
from app.models import AgentPrompt, Dataset, Project
from app.schemas import AgentPlanRequest, AgentRunRequest, Plan
from app.services.ai_agent import DataScienceAgent
from app.services.agent_orchestrator import run_full_lifecycle


router = APIRouter(prefix="/api/projects/{project_id}/agent", tags=["agent"])


@router.post("/plan", response_model=Plan)
async def plan_agent(
    project_id: int,
    payload: AgentPlanRequest,
    session: Session = Depends(get_session),
) -> Plan:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    schema: dict = {}
    if payload.dataset_id is not None:
        ds = session.get(Dataset, payload.dataset_id)
        if not ds or ds.project_id != project_id:
            raise HTTPException(status_code=404, detail="Dataset not found")
        if ds.schema_json:
            try:
                schema = json.loads(ds.schema_json)
            except Exception:
                schema = {}

    agent = DataScienceAgent()
    try:
        plan = await agent.plan_lifecycle(payload.goal, schema)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="The AI planner couldn't generate a plan right now. Please try again, or rephrase your goal.",
        )

    session.add(
        AgentPrompt(
            project_id=project_id,
            tab_name="Question",
            role="user",
            content=payload.goal,
        )
    )
    session.add(
        AgentPrompt(
            project_id=project_id,
            tab_name="Question",
            role="assistant",
            content=json.dumps(plan.model_dump(), ensure_ascii=False),
        )
    )
    session.commit()

    return plan


@router.post("/run")
async def run_agent_lifecycle(
    project_id: int,
    payload: AgentRunRequest,
    session: Session = Depends(get_session),
) -> dict:
    # lightweight existence checks for friendly 404s before orchestration
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    dataset = session.get(Dataset, payload.dataset_id)
    if not dataset or dataset.project_id != project_id:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        return await run_full_lifecycle(
            project_id=project_id,
            dataset_id=payload.dataset_id,
            goal=payload.goal,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="The lifecycle run couldn't complete. Please try again, or run tabs individually.",
        )

