from __future__ import annotations

import json
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.deps import get_session
from app.models import Dataset
from app.schemas import ChartConfig, ExploreChatRequest, ExploreExplainRequest, ExploreInsight
from app.services.ai_agent import DataScienceAgent
from app.services.storage import S3Storage


router = APIRouter(prefix="/api/datasets", tags=["explore"])


def _safe_user_error(message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


def _delimiter_from_key(key: str) -> str:
    lk = key.lower()
    if lk.endswith(".tsv"):
        return "\t"
    return ","


def _load_sample(storage: S3Storage, key: str, delimiter: str, *, nrows: int = 20000) -> pd.DataFrame:
    body = storage.get_object_stream(key)
    try:
        return pd.read_csv(body, sep=delimiter, nrows=nrows)
    except Exception:
        raise _safe_user_error("We couldn't explore this dataset. The file may be malformed or not a CSV.")
    finally:
        try:
            body.close()
        except Exception:
            pass


def _compute_profile(df: pd.DataFrame) -> dict:
    missing_pct = (df.isna().mean() * 100.0).sort_values(ascending=False)
    top_missing = [{"column": str(col), "pct": float(pct)} for col, pct in missing_pct.head(8).items()]

    num = df.select_dtypes(include="number")
    numeric_summary = {}
    if not num.empty:
        desc = num.describe().T
        for col in desc.index[:12]:
            row = desc.loc[col]
            numeric_summary[str(col)] = {
                "min": float(row["min"]),
                "max": float(row["max"]),
                "mean": float(row["mean"]),
                "std": float(row["std"]) if pd.notna(row["std"]) else None,
            }

    top_categories: dict[str, list[dict]] = {}
    non_num_cols = [c for c in df.columns if c not in num.columns]
    for c in non_num_cols[:10]:
        vc = df[c].astype("string").value_counts(dropna=True).head(5)
        top_categories[str(c)] = [{"value": str(idx), "count": int(val)} for idx, val in vc.items()]

    corr_pairs: list[dict] = []
    if num.shape[1] >= 2:
        corr = num.corr(numeric_only=True).abs()
        cols = corr.columns.tolist()
        pairs = []
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                v = float(corr.iloc[i, j])
                pairs.append((v, str(cols[i]), str(cols[j])))
        pairs.sort(reverse=True, key=lambda x: x[0])
        corr_pairs = [{"a": a, "b": b, "abs_r": v} for v, a, b in pairs[:12]]

    return {
        "row_count_sample": int(df.shape[0]),
        "columns": [str(c) for c in df.columns],
        "missing_pct_top": top_missing,
        "numeric_summary": numeric_summary,
        "top_categories": top_categories,
        "correlations_top": corr_pairs,
    }


def _fallback_insights(profile: dict) -> list[ExploreInsight]:
    insights: list[ExploreInsight] = []
    missing = profile.get("missing_pct_top", []) or []
    if missing:
        parts = [f"`{m['column']}` ({m['pct']:.1f}%)" for m in missing if float(m.get("pct", 0)) > 0][:5]
        if parts:
            insights.append(
                ExploreInsight(
                    id=str(uuid4()),
                    type="summary_stats",
                    title="Columns with missing values",
                    description="Missing values appear in: " + ", ".join(parts) + ".",
                    chart_suggestion=None,
                )
            )

    numeric = profile.get("numeric_summary", {}) or {}
    for col, stats in list(numeric.items())[:3]:
        insights.append(
            ExploreInsight(
                id=str(uuid4()),
                type="summary_stats",
                title=f"Summary for {col}",
                description=(
                    f"`{col}` ranges from {stats.get('min', 0):.3g} to {stats.get('max', 0):.3g}, "
                    f"with mean {stats.get('mean', 0):.3g} (sample-based)."
                ),
                chart_suggestion=ChartConfig(
                    id=str(uuid4()),
                    chart_type="histogram",
                    x=col,
                    description=f"Distribution of {col}",
                ),
            )
        )

    corr = profile.get("correlations_top", []) or []
    for pair in corr[:2]:
        if pair.get("abs_r", 0) >= 0.6:
            insights.append(
                ExploreInsight(
                    id=str(uuid4()),
                    type="correlation",
                    title=f"{pair.get('a')} and {pair.get('b')} are related",
                    description=f"These two columns move together in the sample (|r|≈{pair.get('abs_r', 0):.2f}).",
                    chart_suggestion=ChartConfig(
                        id=str(uuid4()),
                        chart_type="scatter",
                        x=str(pair.get("a")),
                        y=str(pair.get("b")),
                        description=f"{pair.get('a')} vs {pair.get('b')}",
                    ),
                )
            )

    if not insights:
        insights.append(
            ExploreInsight(
                id=str(uuid4()),
                type="summary_stats",
                title="Quick scan complete",
                description="No major anomalies detected in this sample. Try asking a focused question in the Explore chat.",
                chart_suggestion=None,
            )
        )
    return insights


def _fallback_questions(profile: dict) -> list[str]:
    cols = profile.get("columns", []) or []
    top_cols = [str(c) for c in cols[:4]]
    return [
        "Which variables look most related to our outcome?",
        "Are there any columns with many missing values we should fix first?",
        "Do any categories dominate the dataset?",
        f"How do distributions differ across {top_cols[0]} groups?" if top_cols else "How do key groups compare?",
        "Are there outliers that may distort model performance?",
    ]


@router.get("/{dataset_id}/explore", response_model=list[ExploreInsight])
async def explore_dataset(dataset_id: int, session: Session = Depends(get_session)) -> list[ExploreInsight]:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        storage = S3Storage()
    except RuntimeError:
        raise _safe_user_error("File storage isn't configured yet. Please set up S3 and try again.", status_code=503)

    delimiter = _delimiter_from_key(ds.s3_key)
    df = _load_sample(storage, ds.s3_key, delimiter, nrows=20000)

    profile = _compute_profile(df)
    try:
        agent = DataScienceAgent()
        raw_items = await agent.suggest_summary_insights(profile)
        insights: list[ExploreInsight] = []
        for item in raw_items:
            try:
                chart_raw = item.get("chart_suggestion")
                chart = None
                if isinstance(chart_raw, dict):
                    chart = ChartConfig(
                        id=str(uuid4()),
                        chart_type=str(chart_raw.get("chart_type", "bar")),
                        x=chart_raw.get("x"),
                        y=chart_raw.get("y"),
                        aggregation=chart_raw.get("aggregation"),
                        description=chart_raw.get("description"),
                    )
                insights.append(
                    ExploreInsight(
                        id=str(uuid4()),
                        type=str(item.get("type", "summary_stats")),
                        title=str(item.get("title", "Insight")),
                        description=str(item.get("description", "")),
                        chart_suggestion=chart,
                    )
                )
            except Exception:
                continue
        if insights:
            return insights
    except Exception:
        pass

    return _fallback_insights(profile)


@router.get("/{dataset_id}/explore/suggested-questions")
async def suggested_explore_questions(dataset_id: int, session: Session = Depends(get_session)) -> dict:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        storage = S3Storage()
    except RuntimeError:
        raise _safe_user_error("File storage isn't configured yet. Please set up S3 and try again.", status_code=503)

    delimiter = _delimiter_from_key(ds.s3_key)
    df = _load_sample(storage, ds.s3_key, delimiter, nrows=5000)
    profile = _compute_profile(df)
    sample_rows = df.head(120).to_dict(orient="records")
    schema = {}
    if ds.schema_json:
        try:
            schema = json.loads(ds.schema_json)
        except Exception:
            schema = {}

    source = "ai"
    try:
        agent = DataScienceAgent()
        questions = await agent.suggest_explore_questions(schema, sample_rows)
    except Exception:
        questions = _fallback_questions(profile)
        source = "heuristic"

    return {"source": source, "questions": questions}


@router.post("/{dataset_id}/explore/chat")
async def chat_explore(dataset_id: int, payload: ExploreChatRequest, session: Session = Depends(get_session)) -> dict:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    question = (payload.question or "").strip()
    if not question:
        raise _safe_user_error("Please enter a question to explore.", status_code=400)

    try:
        storage = S3Storage()
    except RuntimeError:
        raise _safe_user_error("File storage isn't configured yet. Please set up S3 and try again.", status_code=503)

    delimiter = _delimiter_from_key(ds.s3_key)
    df = _load_sample(storage, ds.s3_key, delimiter, nrows=5000)
    profile = _compute_profile(df)
    sample_rows = df.head(120).to_dict(orient="records")
    schema = {}
    if ds.schema_json:
        try:
            schema = json.loads(ds.schema_json)
        except Exception:
            schema = {}

    source = "ai"
    try:
        agent = DataScienceAgent()
        answer = await agent.answer_explore_question(question, schema, sample_rows, profile)
    except Exception:
        source = "heuristic"
        answer = (
            "I couldn't reach the AI assistant right now. Based on a quick sample profile, "
            "start by checking missing-value-heavy columns, strongest correlations, and dominant categories. "
            "If you can, retry in a moment for a more tailored answer."
        )

    return {"source": source, "question": question, "answer": answer}


@router.post("/{dataset_id}/explore/explain")
async def explain_explore_step(dataset_id: int, payload: ExploreExplainRequest) -> dict:
    # dataset_id is included to match frontend routing; we don't need it for explanation,
    # but we keep it for validation symmetry.
    step = payload.step
    if step.tab != "Explore":
        raise _safe_user_error("That step isn't an Explore step.")

    agent = DataScienceAgent()
    try:
        explanation = await agent.explain_step(step)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="The AI explainer couldn't generate an explanation right now. Please try again.",
        )

    return {"explanation": explanation}

