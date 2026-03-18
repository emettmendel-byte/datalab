from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.deps import get_session
from app.models import Dataset, TransformationStep
from app.schemas import CleanRequest, TransformationStepRead
from app.services.cleaning import apply_cleaning_steps


router = APIRouter(prefix="/api/datasets", tags=["clean"])


@router.post("/{dataset_id}/clean")
def clean_dataset(
    dataset_id: int,
    payload: CleanRequest,
    session: Session = Depends(get_session),
) -> dict:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        result = apply_cleaning_steps(ds, payload.steps)
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
    for idx, (step, snippet) in enumerate(zip(payload.steps, result.code_snippets, strict=False)):
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
        "transformation_steps": [TransformationStepRead.model_validate(x) for x in ordered],
    }

