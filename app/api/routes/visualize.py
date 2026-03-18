from __future__ import annotations

import json
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.deps import get_session
from app.models import Dataset, TransformationStep
from app.schemas import ChartConfig, ChartDataRequest, ChartSuggestRequest, TransformationStepRead
from app.services.storage import S3Storage


router = APIRouter(prefix="/api/datasets", tags=["visualize"])


def _safe_user_error(message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


def _delimiter_from_key(key: str) -> str:
    lk = key.lower()
    if lk.endswith(".tsv"):
        return "\t"
    return ","


def _load_sample(storage: S3Storage, key: str, delimiter: str, *, nrows: int = 5000) -> pd.DataFrame:
    body = storage.get_object_stream(key)
    try:
        return pd.read_csv(body, sep=delimiter, nrows=nrows)
    except Exception:
        raise _safe_user_error("We couldn't load chart data. The file may be malformed or not a CSV.")
    finally:
        try:
            body.close()
        except Exception:
            pass


def _parse_schema(schema_json: str | None) -> list[dict]:
    if not schema_json:
        return []
    try:
        obj = json.loads(schema_json)
        cols = obj.get("columns")
        if isinstance(cols, list):
            return [c for c in cols if isinstance(c, dict) and "name" in c]
    except Exception:
        return []
    return []


def _is_numeric(dtype: str) -> bool:
    d = dtype.lower()
    return any(x in d for x in ["int", "float", "double", "number"])


def _is_datetime(dtype: str) -> bool:
    d = dtype.lower()
    return "datetime" in d or "date" in d


def _suggest_charts(question: str, cols: list[dict]) -> list[ChartConfig]:
    q = question.lower()
    numeric = [c["name"] for c in cols if _is_numeric(str(c.get("dtype", "")))]
    datetime_cols = [c["name"] for c in cols if _is_datetime(str(c.get("dtype", "")))]
    non_numeric = [c["name"] for c in cols if c["name"] not in numeric]

    suggestions: list[ChartConfig] = []

    def add(cfg: ChartConfig) -> None:
        if len(suggestions) < 5:
            suggestions.append(cfg)

    if any(k in q for k in ["trend", "over time", "time series", "timeline"]) and datetime_cols:
        x = datetime_cols[0]
        y = numeric[0] if numeric else None
        add(
            ChartConfig(
                id=str(uuid4()),
                chart_type="line",
                x=x,
                y=y,
                aggregation="mean" if y else None,
                filters=None,
                description="See how a value changes over time (sampled).",
            )
        )

    if any(k in q for k in ["relationship", "correl", "vs", "compare"]) and len(numeric) >= 2:
        add(
            ChartConfig(
                id=str(uuid4()),
                chart_type="scatter",
                x=numeric[0],
                y=numeric[1],
                color=non_numeric[0] if non_numeric else None,
                aggregation=None,
                filters=None,
                description="Check whether two numeric columns move together.",
            )
        )

    if numeric:
        add(
            ChartConfig(
                id=str(uuid4()),
                chart_type="histogram",
                x=numeric[0],
                y=None,
                color=None,
                aggregation=None,
                filters=None,
                description="Look at the distribution of a numeric column.",
            )
        )

    if non_numeric and numeric:
        add(
            ChartConfig(
                id=str(uuid4()),
                chart_type="bar",
                x=non_numeric[0],
                y=numeric[0],
                color=None,
                aggregation="mean",
                filters=None,
                description="Compare average values across categories.",
            )
        )
    elif non_numeric:
        add(
            ChartConfig(
                id=str(uuid4()),
                chart_type="bar",
                x=non_numeric[0],
                y=None,
                color=None,
                aggregation="count",
                filters=None,
                description="See how often each category appears.",
            )
        )

    if not suggestions:
        add(
            ChartConfig(
                id=str(uuid4()),
                chart_type="bar",
                x=cols[0]["name"] if cols else None,
                y=None,
                color=None,
                aggregation="count",
                filters=None,
                description="A simple starting chart based on available columns.",
            )
        )

    return suggestions[:5]


def _apply_filters(df: pd.DataFrame, filters: list[dict] | None) -> pd.DataFrame:
    if not filters:
        return df

    out = df
    for f in filters[:10]:
        if not isinstance(f, dict):
            continue
        col = f.get("column")
        op = f.get("op")
        val = f.get("value")
        if not col or col not in out.columns:
            continue

        s = out[col]
        try:
            if op == "==":
                out = out[s == val]
            elif op == "!=":
                out = out[s != val]
            elif op == ">":
                out = out[s > val]
            elif op == ">=":
                out = out[s >= val]
            elif op == "<":
                out = out[s < val]
            elif op == "<=":
                out = out[s <= val]
            elif op == "in":
                out = out[s.isin(list(val or []))]
            elif op == "not_in":
                out = out[~s.isin(list(val or []))]
            elif op == "contains":
                out = out[s.astype("string").str.contains("" if val is None else str(val), na=False)]
        except Exception:
            continue

    return out


def _chart_data(df: pd.DataFrame, cfg: ChartConfig) -> dict:
    chart_type = cfg.chart_type
    x = cfg.x
    y = cfg.y

    if chart_type == "histogram":
        if not x or x not in df.columns:
            raise _safe_user_error("This chart config is missing an x column.")
        series = df[x].dropna()
        return {"type": "histogram", "x": series.tolist()}

    if chart_type == "scatter":
        if not x or not y or x not in df.columns or y not in df.columns:
            raise _safe_user_error("This chart config needs both x and y columns.")
        out = {"type": "scatter", "x": df[x].tolist(), "y": df[y].tolist()}
        if cfg.color and cfg.color in df.columns:
            out["color"] = df[cfg.color].astype("string").tolist()
        return out

    if chart_type in {"bar", "line"}:
        if not x or x not in df.columns:
            raise _safe_user_error("This chart config is missing an x column.")

        agg = (cfg.aggregation or "count").lower()
        if y and y in df.columns and agg != "count":
            g = df.groupby(x, dropna=False)[y]
            if agg == "mean":
                ser = g.mean()
            elif agg == "sum":
                ser = g.sum()
            elif agg == "median":
                ser = g.median()
            else:
                ser = g.mean()
        else:
            ser = df[x].value_counts(dropna=False)
            ser = ser.sort_index()

        xs = [str(i) for i in ser.index.tolist()]
        ys = ser.tolist()
        return {"type": chart_type, "x": xs, "y": ys}

    raise _safe_user_error("Unsupported chart type.")


@router.post("/{dataset_id}/charts/suggest", response_model=list[ChartConfig])
def suggest_charts(dataset_id: int, payload: ChartSuggestRequest, session: Session = Depends(get_session)) -> list[ChartConfig]:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    cols = _parse_schema(ds.schema_json)
    if not cols:
        # Fallback to a small sample to infer columns if schema is missing.
        try:
            storage = S3Storage()
        except RuntimeError:
            raise _safe_user_error("File storage isn't configured yet. Please set up S3 and try again.", status_code=503)
        delimiter = _delimiter_from_key(ds.s3_key)
        df = _load_sample(storage, ds.s3_key, delimiter, nrows=500)
        cols = [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns]

    return _suggest_charts(payload.question, cols)


@router.post("/{dataset_id}/charts/data")
def chart_data(dataset_id: int, payload: ChartDataRequest, session: Session = Depends(get_session)) -> dict:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        storage = S3Storage()
    except RuntimeError:
        raise _safe_user_error("File storage isn't configured yet. Please set up S3 and try again.", status_code=503)

    delimiter = _delimiter_from_key(ds.s3_key)
    df = _load_sample(storage, ds.s3_key, delimiter, nrows=5000)

    cfg = payload.config
    df = _apply_filters(df, cfg.filters)

    data = _chart_data(df, cfg)

    # Store selection as a TransformationStep (Visualize)
    max_idx = session.exec(
        select(TransformationStep.step_index)
        .where(TransformationStep.dataset_id == ds.id)
        .where(TransformationStep.tab_name == "Visualize")
        .order_by(TransformationStep.step_index.desc())
        .limit(1)
    ).first()
    next_idx = int(max_idx) + 1 if max_idx is not None else 0

    ts = TransformationStep(
        dataset_id=ds.id,
        tab_name="Visualize",
        step_index=next_idx,
        code_snippet=json.dumps(cfg.model_dump(), ensure_ascii=False),
        description=cfg.description or "Chart selection",
    )
    session.add(ts)
    session.commit()
    session.refresh(ts)

    return {
        "config": cfg,
        "plotly": data,
        "transformation_step": TransformationStepRead.model_validate(ts),
    }

