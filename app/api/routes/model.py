from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.deps import get_session
from app.models import Dataset, ModelRun
from app.schemas import ModelPredictRequest, ModelTrainRequest
from app.services.modeling import load_model_from_s3, train_model


router = APIRouter(prefix="/api", tags=["model"])


@router.post("/datasets/{dataset_id}/models/train")
def train_dataset_model(
    dataset_id: int,
    payload: ModelTrainRequest,
    session: Session = Depends(get_session),
) -> dict:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        model_run, _metrics = train_model(ds, payload.goal, session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=503, detail="File storage isn't configured yet. Please set up S3 and try again.")
    except Exception:
        raise HTTPException(status_code=500, detail="Model training failed. Try simplifying your goal or using a smaller dataset.")

    return {
        "model_run_id": model_run.id,
        "config_json": model_run.config_json,
        "metrics_json": model_run.metrics_json,
    }


@router.post("/models/{model_run_id}/predict")
def predict_model(
    model_run_id: int,
    payload: ModelPredictRequest,
    session: Session = Depends(get_session),
) -> dict:
    mr = session.get(ModelRun, model_run_id)
    if not mr:
        raise HTTPException(status_code=404, detail="Model run not found")
    if not mr.s3_model_key:
        raise HTTPException(status_code=400, detail="This model run has no saved model artifact.")

    config = {}
    if mr.config_json:
        try:
            config = json.loads(mr.config_json)
        except Exception:
            config = {}

    try:
        model = load_model_from_s3(mr.s3_model_key)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="File storage isn't configured yet. Please set up S3 and try again.")
    except Exception:
        raise HTTPException(status_code=500, detail="Couldn't load the saved model. Please retrain.")

    row = payload.row or {}
    import pandas as pd

    X = pd.DataFrame([row])

    try:
        pred = model.predict(X)
        prediction = pred[0] if hasattr(pred, "__len__") else pred
    except Exception:
        raise HTTPException(status_code=400, detail="That row doesn't match what the model expects. Check column names and types.")

    out: dict = {"prediction": prediction, "task_type": config.get("task_type")}

    # Probabilities when applicable
    try:
        if hasattr(model, "predict_proba") and config.get("task_type") == "classification":
            proba = model.predict_proba(X)[0]
            classes = None
            try:
                classes = list(getattr(model, "classes_"))
            except Exception:
                classes = None
            if classes is not None and len(classes) == len(proba):
                out["probabilities"] = {str(c): float(p) for c, p in zip(classes, proba, strict=False)}
            else:
                out["probabilities"] = [float(p) for p in proba]
    except Exception:
        pass

    return out

