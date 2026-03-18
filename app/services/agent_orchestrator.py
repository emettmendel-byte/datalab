from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.api.routes.dataset_preview import preview_dataset
from app.api.routes.explore import explore_dataset
from app.api.routes.report import generate_report as generate_report_endpoint
from app.api.routes.visualize import suggest_charts
from app.deps import engine
from app.models import AgentPrompt, Dataset, Project, TransformationStep
from app.schemas import ChartSuggestRequest, CleaningOperationType, CleaningStep
from app.services.ai_agent import DataScienceAgent
from app.services.cleaning import apply_cleaning_steps
from app.services.modeling import train_model


logger = logging.getLogger(__name__)
TOTAL_BUDGET_SECONDS = 120.0


async def run_full_lifecycle(project_id: int, dataset_id: int, goal: str) -> dict:
    started = time.monotonic()
    deadline = started + TOTAL_BUDGET_SECONDS
    timings: dict[str, float] = {}

    out: dict[str, Any] = {
        "question_plan": None,
        "data_preview": None,
        "clean_summary": None,
        "explore_insights": None,
        "visualize_configs": None,
        "model_summary": None,
        "report": None,
    }

    with Session(engine) as session:
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        dataset = session.get(Dataset, dataset_id)
        if not dataset or dataset.project_id != project_id:
            raise HTTPException(status_code=404, detail="Dataset not found")

        plan = None
        explore_insights: list[dict] = []

        # QUESTION
        if _remaining(deadline) > 0:
            t0 = time.monotonic()
            try:
                schema = _parse_json_obj(dataset.schema_json)
                agent = DataScienceAgent()
                plan = await agent.plan_lifecycle(goal, schema)
                session.add(AgentPrompt(project_id=project_id, tab_name="Question", role="user", content=goal))
                session.add(
                    AgentPrompt(
                        project_id=project_id,
                        tab_name="Question",
                        role="assistant",
                        content=json.dumps(plan.model_dump(), ensure_ascii=False),
                    )
                )
                session.commit()
                out["question_plan"] = plan.model_dump()
            except Exception:
                logger.exception("QUESTION step failed project_id=%s dataset_id=%s", project_id, dataset_id)
                out["question_plan"] = {"message": "The AI planner couldn't finish this step. You can still continue with manual tabs."}
            timings["question"] = time.monotonic() - t0
        else:
            out["question_plan"] = {"message": "Skipped due to time budget."}

        # DATA
        if _remaining(deadline) > 0:
            t0 = time.monotonic()
            try:
                out["data_preview"] = preview_dataset(dataset_id=dataset_id, page=1, page_size=50, session=session)
            except Exception:
                logger.exception("DATA step failed project_id=%s dataset_id=%s", project_id, dataset_id)
                out["data_preview"] = {"message": "We couldn't prepare a data preview right now."}
            timings["data"] = time.monotonic() - t0
        else:
            out["data_preview"] = {"message": "Skipped due to time budget."}

        # CLEAN
        if _remaining(deadline) > 10:
            t0 = time.monotonic()
            try:
                clean_steps = _extract_clean_steps(plan)
                if clean_steps:
                    out["clean_summary"] = _run_clean_steps(session, dataset, clean_steps)
                else:
                    out["clean_summary"] = {"message": "No safe cleaning steps were found in the plan."}
            except Exception:
                logger.exception("CLEAN step failed project_id=%s dataset_id=%s", project_id, dataset_id)
                out["clean_summary"] = {"message": "We couldn't complete automatic cleaning. You can still clean manually."}
            timings["clean"] = time.monotonic() - t0
            session.refresh(dataset)
        else:
            out["clean_summary"] = {"message": "Skipped due to time budget."}

        # EXPLORE
        if _remaining(deadline) > 8:
            t0 = time.monotonic()
            try:
                insights = explore_dataset(dataset_id=dataset_id, session=session)
                explore_insights = [x.model_dump() for x in insights]
                out["explore_insights"] = explore_insights
            except Exception:
                logger.exception("EXPLORE step failed project_id=%s dataset_id=%s", project_id, dataset_id)
                out["explore_insights"] = [{"message": "We couldn't generate insights right now."}]
            timings["explore"] = time.monotonic() - t0
        else:
            out["explore_insights"] = [{"message": "Skipped due to time budget."}]

        # VISUALIZE
        if _remaining(deadline) > 6:
            t0 = time.monotonic()
            try:
                question_text = _build_visualize_prompt(goal, plan, explore_insights)
                cfgs = suggest_charts(
                    dataset_id=dataset_id,
                    payload=ChartSuggestRequest(question=question_text),
                    session=session,
                )
                out["visualize_configs"] = [c.model_dump() for c in cfgs]
            except Exception:
                logger.exception("VISUALIZE step failed project_id=%s dataset_id=%s", project_id, dataset_id)
                out["visualize_configs"] = [{"message": "We couldn't suggest charts right now."}]
            timings["visualize"] = time.monotonic() - t0
        else:
            out["visualize_configs"] = [{"message": "Skipped due to time budget."}]

        # MODEL
        model_run_id: int | None = None
        if _remaining(deadline) > 25:
            t0 = time.monotonic()
            try:
                model_run, metrics = train_model(dataset, goal, session)
                model_run_id = model_run.id
                out["model_summary"] = {
                    "model_run_id": model_run.id,
                    "config_json": model_run.config_json,
                    "metrics_json": model_run.metrics_json,
                    "metrics": metrics,
                }
            except Exception:
                logger.exception("MODEL step failed project_id=%s dataset_id=%s", project_id, dataset_id)
                out["model_summary"] = {"message": "Model training didn't finish in time. Try a simpler goal or run Model tab directly."}
            timings["model"] = time.monotonic() - t0
        else:
            out["model_summary"] = {"message": "Skipped due to time budget."}

        # REPORT
        if model_run_id is not None and _remaining(deadline) > 8:
            t0 = time.monotonic()
            try:
                out["report"] = await generate_report_endpoint(model_run_id=model_run_id, session=session)
            except Exception:
                logger.exception("REPORT step failed project_id=%s dataset_id=%s", project_id, dataset_id)
                out["report"] = {"message": "We couldn't generate the narrative report right now."}
            timings["report"] = time.monotonic() - t0
        elif model_run_id is None:
            out["report"] = {"message": "Skipped because no model was trained."}
        else:
            out["report"] = {"message": "Skipped due to time budget."}

    logger.info("Lifecycle run completed project_id=%s dataset_id=%s timings=%s", project_id, dataset_id, timings)
    return out


def _remaining(deadline: float) -> float:
    return deadline - time.monotonic()


def _parse_json_obj(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _extract_clean_steps(plan) -> list[CleaningStep]:
    if not plan or not getattr(plan, "steps", None):
        return []

    mapping = {
        "drop_columns": CleaningOperationType.DROP_COLUMNS,
        "drop_rows_with_missing": CleaningOperationType.DROP_ROWS_WITH_MISSING,
        "fill_missing": CleaningOperationType.FILL_MISSING,
        "cast_type": CleaningOperationType.CAST_TYPE,
        "filter_rows": CleaningOperationType.FILTER_ROWS,
        "dedup_rows": CleaningOperationType.DEDUP_ROWS,
        "standardize_categories": CleaningOperationType.STANDARDIZE_CATEGORIES,
        "parse_dates": CleaningOperationType.PARSE_DATES,
    }

    out: list[CleaningStep] = []
    for s in plan.steps:
        if s.tab != "Clean":
            continue
        op_raw = (s.operation_type or "").strip()
        op_key = op_raw.lower()
        op = None
        if op_raw in CleaningOperationType.__members__:
            op = CleaningOperationType[op_raw]
        elif op_key in mapping:
            op = mapping[op_key]
        else:
            continue

        out.append(
            CleaningStep(
                operation_type=op,
                parameters={},
                description=s.user_friendly_explanation or s.short_title or "Applied clean step",
                generated_code=s.python_pandas_code,
            )
        )
    return out


def _run_clean_steps(session: Session, dataset: Dataset, steps: list[CleaningStep]) -> dict:
    result = apply_cleaning_steps(dataset, steps)
    dataset.s3_key = result.new_s3_key
    dataset.schema_json = result.schema_json
    dataset.row_count = result.row_count
    session.add(dataset)
    session.commit()
    session.refresh(dataset)

    max_idx = session.exec(
        select(TransformationStep.step_index)
        .where(TransformationStep.dataset_id == dataset.id)
        .where(TransformationStep.tab_name == "Clean")
        .order_by(TransformationStep.step_index.desc())
        .limit(1)
    ).first()
    next_idx = int(max_idx) + 1 if max_idx is not None else 0

    created_ids = []
    for offset, (step, snippet) in enumerate(zip(steps, result.code_snippets, strict=False)):
        ts = TransformationStep(
            dataset_id=dataset.id,
            tab_name="Clean",
            step_index=next_idx + offset,
            code_snippet=snippet,
            description=step.description,
        )
        session.add(ts)
        session.flush()
        created_ids.append(ts.id)
    session.commit()

    return {
        "updated_s3_key": dataset.s3_key,
        "schema_json": dataset.schema_json,
        "preview_rows": result.preview_rows,
        "applied_steps": len(steps),
        "transformation_step_ids": created_ids,
    }


def _build_visualize_prompt(goal: str, plan, explore_insights: list[dict]) -> str:
    plan_titles = []
    if plan and getattr(plan, "steps", None):
        for s in plan.steps:
            if s.tab == "Visualize" and s.short_title:
                plan_titles.append(s.short_title)
    insight_titles = [x.get("title") for x in explore_insights[:3] if isinstance(x, dict) and x.get("title")]
    parts = [goal]
    if plan_titles:
        parts.append("Planned visuals: " + ", ".join(plan_titles))
    if insight_titles:
        parts.append("Interesting findings: " + ", ".join(insight_titles))
    return " | ".join(parts)

