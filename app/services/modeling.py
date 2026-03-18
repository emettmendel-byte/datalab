from __future__ import annotations

import io
import json
import math
from typing import Any
from uuid import uuid4

import joblib
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_squared_error,
    r2_score,
    silhouette_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlmodel import Session, select

from app.models import Dataset, ModelRun, TransformationStep
from app.services.storage import S3Storage


def infer_task_and_target(goal: str, schema_json: dict, sample_df: pd.DataFrame) -> tuple[str, str | None]:
    """
    Returns (task_type, target_column)
    task_type in {"classification","regression","clustering"}
    """
    g = (goal or "").lower()

    cols: list[str] = []
    if isinstance(schema_json, dict):
        c = schema_json.get("columns")
        if isinstance(c, list):
            cols = [str(x.get("name")) for x in c if isinstance(x, dict) and x.get("name")]
    if not cols:
        cols = sample_df.columns.astype(str).tolist()

    if any(k in g for k in ["cluster", "segment", "group similar", "unsupervised"]):
        return "clustering", None

    for col in cols:
        c_low = col.lower()
        if f"predict {c_low}" in g or f"target {c_low}" in g or f"predicting {c_low}" in g:
            return _guess_supervised_task(g, sample_df[col] if col in sample_df.columns else sample_df.iloc[:, -1]), col

    preferred = ["target", "label", "y", "outcome", "class", "churn", "fraud", "price", "revenue", "sales"]
    for name in preferred:
        for col in cols:
            if col.lower() == name:
                return _guess_supervised_task(g, sample_df[col] if col in sample_df.columns else sample_df.iloc[:, -1]), col

    if any(k in g for k in ["predict", "forecast", "estimate", "classify", "probability", "risk"]):
        if cols:
            col = cols[-1]
            ser = sample_df[col] if col in sample_df.columns else sample_df.iloc[:, -1]
            return _guess_supervised_task(g, ser), col

    return "clustering", None


def _guess_supervised_task(goal_lower: str, y: pd.Series) -> str:
    if any(k in goal_lower for k in ["regress", "estimate", "forecast", "predict value", "price", "amount"]):
        return "regression"

    try:
        nunique = int(y.nunique(dropna=True))
        if nunique <= 20:
            return "classification"
    except Exception:
        pass
    return "regression"


def train_model(dataset: Dataset, goal: str, session: Session) -> tuple[ModelRun, dict]:
    storage = S3Storage()
    delimiter = "\t" if dataset.s3_key.lower().endswith(".tsv") else ","

    max_rows = 50_000
    if isinstance(dataset.row_count, int) and dataset.row_count > 1_000_000:
        max_rows = 30_000

    body = storage.get_object_stream(dataset.s3_key)
    try:
        df = pd.read_csv(body, sep=delimiter, nrows=max_rows)
    except Exception as e:
        raise ValueError("We couldn't load this dataset for modeling. Please check that it's a valid CSV.") from e
    finally:
        try:
            body.close()
        except Exception:
            pass

    schema_obj: dict = {}
    if dataset.schema_json:
        try:
            schema_obj = json.loads(dataset.schema_json)
        except Exception:
            schema_obj = {}

    task_type, target = infer_task_and_target(goal, schema_obj, df)

    config: dict[str, Any] = {
        "task_type": task_type,
        "target_column": target,
        "dataset_id": dataset.id,
        "project_id": dataset.project_id,
        "goal": goal,
        "sample_rows": int(df.shape[0]),
    }
    metrics: dict[str, Any] = {}

    if task_type == "clustering":
        X = _prepare_features(df, target_column=None)
        X = X.select_dtypes(include="number")
        if X.shape[1] == 0 or X.shape[0] < 10:
            raise ValueError("Not enough usable numeric data to cluster.")

        n_clusters = int(min(6, max(2, math.sqrt(X.shape[0]) // 3)))
        model = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler(with_mean=False)),
                ("kmeans", KMeans(n_clusters=n_clusters, n_init="auto", random_state=42)),
            ]
        )
        model.fit(X)
        labels = model.named_steps["kmeans"].labels_
        metrics["inertia"] = float(model.named_steps["kmeans"].inertia_)
        try:
            metrics["silhouette"] = float(silhouette_score(X, labels))
        except Exception:
            metrics["silhouette"] = None
        config.update({"algorithm": "KMeans", "n_clusters": n_clusters, "features": list(X.columns)})

    else:
        if not target or target not in df.columns:
            raise ValueError("Couldn't determine which column to predict. Try mentioning the target column in your goal.")

        y = df[target]
        X = _prepare_features(df, target_column=target)
        if X.shape[1] == 0:
            raise ValueError("No usable feature columns found after removing the target.")

        numeric_features = X.select_dtypes(include="number").columns.tolist()
        categorical_features = [c for c in X.columns if c not in numeric_features]

        preprocessor = ColumnTransformer(
            transformers=[
                ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric_features),
                ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("ohe", OneHotEncoder(handle_unknown="ignore"))]), categorical_features),
            ],
            remainder="drop",
        )

        if task_type == "classification":
            alg = "LogisticRegression"
            base = LogisticRegression(max_iter=500)
            if X.shape[0] > 20_000 or X.shape[1] > 50:
                alg = "RandomForestClassifier"
                base = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)

            model = Pipeline(steps=[("prep", preprocessor), ("model", base)])

            strat = y if y.nunique(dropna=True) <= 20 else None
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=strat)
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            metrics["accuracy"] = float(accuracy_score(y_test, y_pred))
            try:
                metrics["f1_weighted"] = float(f1_score(y_test, y_pred, average="weighted"))
            except Exception:
                metrics["f1_weighted"] = None
            try:
                metrics["confusion_matrix"] = confusion_matrix(y_test, y_pred).tolist()
            except Exception:
                metrics["confusion_matrix"] = None

            config.update(
                {
                    "algorithm": alg,
                    "features": list(X.columns),
                    "numeric_features": numeric_features,
                    "categorical_features": categorical_features,
                }
            )

        else:
            alg = "LinearRegression"
            base = LinearRegression()
            if X.shape[0] > 20_000 or X.shape[1] > 50:
                alg = "RandomForestRegressor"
                base = RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=-1)

            model = Pipeline(steps=[("prep", preprocessor), ("model", base)])
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            metrics["r2"] = float(r2_score(y_test, y_pred))
            metrics["rmse"] = float(mean_squared_error(y_test, y_pred, squared=False))

            config.update(
                {
                    "algorithm": alg,
                    "features": list(X.columns),
                    "numeric_features": numeric_features,
                    "categorical_features": categorical_features,
                }
            )

    key = f"projects/{dataset.project_id}/models/{uuid4()}.joblib"
    buf = io.BytesIO()
    joblib.dump(model, buf)
    buf.seek(0)
    storage.put_fileobj(buf, key=key, content_type="application/octet-stream")

    model_run = ModelRun(
        project_id=dataset.project_id,
        dataset_id=dataset.id,
        config_json=json.dumps(config, ensure_ascii=False),
        metrics_json=json.dumps(metrics, ensure_ascii=False),
        s3_model_key=key,
        status="completed",
    )
    session.add(model_run)
    session.commit()
    session.refresh(model_run)

    next_idx = _next_step_index(session, dataset.id, "Model")
    summary = {
        "model_run_id": model_run.id,
        "algorithm": config.get("algorithm"),
        "task_type": task_type,
        "target": target,
        "features": config.get("features"),
    }
    ts = TransformationStep(
        dataset_id=dataset.id,
        tab_name="Model",
        step_index=next_idx,
        code_snippet=json.dumps(summary, ensure_ascii=False),
        description=f"Trained {config.get('algorithm')} ({task_type})",
    )
    session.add(ts)
    session.commit()

    return model_run, metrics


def load_model_from_s3(model_key: str):
    storage = S3Storage()
    body = storage.get_object_stream(model_key)
    try:
        data = body.read()
    finally:
        try:
            body.close()
        except Exception:
            pass
    return joblib.load(io.BytesIO(data))


def _next_step_index(session: Session, dataset_id: int, tab_name: str) -> int:
    max_idx = session.exec(
        select(TransformationStep.step_index)
        .where(TransformationStep.dataset_id == dataset_id)
        .where(TransformationStep.tab_name == tab_name)
        .order_by(TransformationStep.step_index.desc())
        .limit(1)
    ).first()
    return int(max_idx) + 1 if max_idx is not None else 0


def _prepare_features(df: pd.DataFrame, *, target_column: str | None) -> pd.DataFrame:
    X = df.copy()
    if target_column and target_column in X.columns:
        X = X.drop(columns=[target_column])
    X = X.dropna(axis=1, how="all")
    return X


class ModelingService:
    """
    Placeholder for AutoML-light sklearn workflows.
    """

    pass

