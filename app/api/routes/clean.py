from __future__ import annotations

import json

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.deps import get_session
from app.models import Dataset, TransformationStep
from app.schemas import CleanRequest, CleanSuggestRequest, CleaningOperationType, CleaningStep, TransformationStepRead
from app.services.ai_agent import DataScienceAgent
from app.services.cleaning import apply_cleaning_steps
from app.services.storage import S3Storage


router = APIRouter(prefix="/api/datasets", tags=["clean"])


def _load_sample_rows(ds: Dataset, nrows: int = 200) -> list[dict]:
    storage = S3Storage()
    delimiter = "\t" if ds.s3_key.lower().endswith(".tsv") else ","
    body = storage.get_object_stream(ds.s3_key)
    try:
        df = pd.read_csv(body, sep=delimiter, nrows=nrows)
    finally:
        try:
            body.close()
        except Exception:
            pass
    return df.to_dict(orient="records")


def _preview_page(ds: Dataset, page: int = 1, page_size: int = 50) -> dict:
    storage = S3Storage()
    delimiter = "\t" if ds.s3_key.lower().endswith(".tsv") else ","
    skip = (page - 1) * page_size
    body = storage.get_object_stream(ds.s3_key)
    try:
        df = pd.read_csv(body, sep=delimiter, skiprows=range(1, skip + 1), nrows=page_size)
    finally:
        try:
            body.close()
        except Exception:
            pass
    return {
        "page": page,
        "page_size": page_size,
        "columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns],
        "rows": df.to_dict(orient="records"),
    }


def _heuristic_messiness_report(ds: Dataset) -> str:
    try:
        sample = _load_sample_rows(ds, 250)
        if not sample:
            return "I couldn't find enough rows to diagnose quality issues yet."
        df = pd.DataFrame(sample)
        missing_pct = (df.isna().mean() * 100.0).sort_values(ascending=False)
        top_missing = [f"{c} ({p:.1f}%)" for c, p in missing_pct.items() if p > 0][:4]
        duplicate_count = int(df.duplicated().sum())
        msg = []
        if top_missing:
            msg.append("Likely messy areas include missing values in: " + ", ".join(top_missing) + ".")
        if duplicate_count > 0:
            msg.append(f"I found possible duplicate rows in the sample ({duplicate_count} duplicates).")
        obj_cols = df.select_dtypes(exclude="number").columns.tolist()
        if obj_cols:
            msg.append(f"Text columns like {obj_cols[0]} may need standardization (trim/case consistency).")
        msg.append("Recommended first steps: fill critical missing fields, remove duplicates, and normalize category text.")
        return " ".join(msg)
    except Exception:
        return "I couldn't diagnose messiness automatically right now. Try refreshing and asking again."


def _extract_clean_steps_from_plan(plan) -> list[CleaningStep]:
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
    for step in plan.steps:
        if step.tab != "Clean":
            continue
        op_raw = (step.operation_type or "").strip()
        op = None
        if op_raw in CleaningOperationType.__members__:
            op = CleaningOperationType[op_raw]
        else:
            op = mapping.get(op_raw.lower())
        if not op:
            continue
        out.append(
            CleaningStep(
                operation_type=op,
                parameters={},
                description=step.user_friendly_explanation or step.short_title,
                generated_code=step.python_pandas_code,
            )
        )
    return out


def _heuristic_clean_suggestions(ds: Dataset) -> list[CleaningStep]:
    suggestions: list[CleaningStep] = []
    storage = S3Storage()
    delimiter = "\t" if ds.s3_key.lower().endswith(".tsv") else ","

    body = storage.get_object_stream(ds.s3_key)
    try:
        df = pd.read_csv(body, sep=delimiter, nrows=2000)
    finally:
        try:
            body.close()
        except Exception:
            pass

    missing_pct = (df.isna().mean() * 100.0).sort_values(ascending=False)
    missing_cols = [str(c) for c, pct in missing_pct.items() if pct > 15][:3]
    if missing_cols:
        suggestions.append(
            CleaningStep(
                operation_type=CleaningOperationType.FILL_MISSING,
                parameters={"strategy": "median", "columns": missing_cols},
                description=f"Fill missing values in {', '.join(missing_cols)} with safe defaults.",
            )
        )

    if int(df.duplicated().sum()) > 0:
        suggestions.append(
            CleaningStep(
                operation_type=CleaningOperationType.DEDUP_ROWS,
                parameters={},
                description="Remove duplicate rows to avoid counting the same record multiple times.",
            )
        )

    object_cols = df.select_dtypes(exclude="number").columns.tolist()
    if object_cols:
        col = str(object_cols[0])
        suggestions.append(
            CleaningStep(
                operation_type=CleaningOperationType.STANDARDIZE_CATEGORIES,
                parameters={"column": col, "strip": True, "lower": True},
                description=f"Standardize text values in {col} to reduce inconsistent category labels.",
            )
        )

    date_like = [c for c in object_cols if "date" in str(c).lower() or "time" in str(c).lower()]
    if date_like:
        suggestions.append(
            CleaningStep(
                operation_type=CleaningOperationType.PARSE_DATES,
                parameters={"column": str(date_like[0])},
                description=f"Parse {date_like[0]} as dates for reliable time-based analysis.",
            )
        )

    if not suggestions:
        suggestions.append(
            CleaningStep(
                operation_type=CleaningOperationType.DEDUP_ROWS,
                parameters={},
                description="Run a basic duplicate check before modeling.",
            )
        )

    return suggestions[:6]


@router.post("/{dataset_id}/clean/suggest")
async def suggest_clean_steps(
    dataset_id: int,
    payload: CleanSuggestRequest,
    session: Session = Depends(get_session),
) -> dict:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    schema = {}
    if ds.schema_json:
        try:
            schema = json.loads(ds.schema_json)
        except Exception:
            schema = {}

    instruction = (payload.instruction or "").strip()
    if not instruction:
        instruction = "Suggest safe cleaning steps for this dataset."

    source = "ai"
    try:
        agent = DataScienceAgent()
        sample_rows = _load_sample_rows(ds, 150)
        steps = await agent.suggest_cleaning_steps(
            instruction=instruction,
            dataset_schema=schema,
            sample_rows=sample_rows,
            existing_steps=None,
        )
    except Exception:
        steps = []
        source = "heuristic"

    if not steps:
        steps = _heuristic_clean_suggestions(ds)
        source = "heuristic"

    return {
        "source": source,
        "instruction": instruction,
        "steps": [s.model_dump() for s in steps],
    }


@router.post("/{dataset_id}/clean/diagnose")
async def diagnose_clean_data(
    dataset_id: int,
    payload: CleanSuggestRequest,
    session: Session = Depends(get_session),
) -> dict:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    schema = {}
    if ds.schema_json:
        try:
            schema = json.loads(ds.schema_json)
        except Exception:
            schema = {}

    instruction = (payload.instruction or "").strip()
    if not instruction:
        instruction = "Where is this dataset messy, and what should I clean first?"

    try:
        sample_rows = _load_sample_rows(ds, 150)
        agent = DataScienceAgent()
        message = await agent.diagnose_data_messiness(
            instruction=instruction,
            dataset_schema=schema,
            sample_rows=sample_rows,
        )
        source = "ai"
    except Exception:
        message = _heuristic_messiness_report(ds)
        source = "heuristic"

    return {
        "source": source,
        "instruction": instruction,
        "message": message,
    }


@router.post("/{dataset_id}/clean")
async def clean_dataset(
    dataset_id: int,
    payload: CleanRequest,
    session: Session = Depends(get_session),
) -> dict:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    instruction = (payload.instruction or "").strip()
    before_row_count = ds.row_count
    steps_to_apply = payload.steps
    used_ollama = False

    # Always try to call Ollama with sample data + user instruction before execution.
    # If Ollama is unavailable, fall back to provided steps.
    if instruction or steps_to_apply:
        try:
            schema = {}
            if ds.schema_json:
                try:
                    schema = json.loads(ds.schema_json)
                except Exception:
                    schema = {}
            sample_rows = _load_sample_rows(ds, 150)
            agent = DataScienceAgent()
            steps_to_apply = await agent.suggest_cleaning_steps(
                instruction=instruction or "Apply these user-selected cleaning steps safely.",
                dataset_schema=schema,
                sample_rows=sample_rows,
                existing_steps=[s.model_dump() for s in payload.steps],
            )
            used_ollama = True
        except Exception:
            steps_to_apply = payload.steps

    before_preview = _preview_page(ds, page=1, page_size=50)
    before_window_rows = _load_sample_rows(ds, 500)

    try:
        result = apply_cleaning_steps(ds, steps_to_apply)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="File storage isn't configured yet. Please set up S3 and try again.",
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Cleaning failed. Try fewer/simpler steps, or preview the dataset to confirm it's valid.",
        )

    ds.s3_key = result.new_s3_key
    ds.schema_json = result.schema_json
    ds.row_count = result.row_count
    session.add(ds)
    session.commit()
    session.refresh(ds)

    steps_out: list[TransformationStep] = []
    for idx, (step, snippet) in enumerate(zip(steps_to_apply, result.code_snippets, strict=False)):
        ts = TransformationStep(
            dataset_id=ds.id,
            tab_name="Clean",
            step_index=idx,
            code_snippet=snippet,
            description=step.description,
        )
        session.add(ts)
        steps_out.append(ts)

    session.commit()
    for ts in steps_out:
        session.refresh(ts)

    ordered = list(
        session.exec(
            select(TransformationStep)
            .where(TransformationStep.dataset_id == ds.id)
            .where(TransformationStep.tab_name == "Clean")
            .order_by(TransformationStep.step_index.asc(), TransformationStep.created_at.asc())
        )
    )

    return {
        "dataset_id": ds.id,
        "s3_key": ds.s3_key,
        "schema_json": ds.schema_json,
        "rows": result.preview_rows,
        "applied_steps": [s.model_dump() for s in steps_to_apply],
        "execution_source": "ollama" if used_ollama else "selected_steps_fallback",
        "row_count_before": before_row_count,
        "row_count_after": ds.row_count,
        "before_preview": before_preview,
        "before_window_rows": before_window_rows,
        "after_preview": _preview_page(ds, page=1, page_size=50),
        "transformation_steps": [TransformationStepRead.model_validate(x) for x in ordered],
    }

