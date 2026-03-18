from __future__ import annotations

import json
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.deps import get_session
from app.models import Dataset
from app.schemas import ChartConfig, ExploreExplainRequest, ExploreInsight
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


@router.get("/{dataset_id}/explore", response_model=list[ExploreInsight])
def explore_dataset(dataset_id: int, session: Session = Depends(get_session)) -> list[ExploreInsight]:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        storage = S3Storage()
    except RuntimeError:
        raise _safe_user_error("File storage isn't configured yet. Please set up S3 and try again.", status_code=503)

    delimiter = _delimiter_from_key(ds.s3_key)
    df = _load_sample(storage, ds.s3_key, delimiter, nrows=20000)

    insights: list[ExploreInsight] = []

    # Missingness + type hints
    missing_pct = (df.isna().mean() * 100.0).sort_values(ascending=False)
    top_missing = missing_pct[missing_pct > 0].head(5)
    if not top_missing.empty:
        parts = [f"`{col}` ({pct:.1f}%)" for col, pct in top_missing.items()]
        insights.append(
            ExploreInsight(
                id=str(uuid4()),
                type="summary_stats",
                title="Missing values to review",
                description="Some columns have missing values: " + ", ".join(parts) + ".",
                chart_suggestion=None,
            )
        )

    # Numeric summaries
    num = df.select_dtypes(include="number")
    if not num.empty:
        desc = num.describe().T
        # Pick 3 columns with highest std (often most informative)
        cols = desc.sort_values("std", ascending=False).head(3).index.tolist()
        for c in cols:
            row = desc.loc[c]
            insights.append(
                ExploreInsight(
                    id=str(uuid4()),
                    type="summary_stats",
                    title=f"Quick stats for {c}",
                    description=(
                        f"`{c}` ranges from {row['min']:.3g} to {row['max']:.3g} "
                        f"with an average around {row['mean']:.3g} (sample-based)."
                    ),
                    chart_suggestion=ChartConfig(
                        id=str(uuid4()),
                        chart_type="histogram",
                        x=c,
                        description=f"Distribution of {c}",
                    ),
                )
            )

    # Categorical cardinality
    non_num_cols = [c for c in df.columns if c not in num.columns]
    for c in non_num_cols[:25]:
        s = df[c]
        # Treat low-unique object columns as categorical suggestions
        nunique = int(s.nunique(dropna=True))
        if 2 <= nunique <= 30:
            top = s.astype("string").value_counts(dropna=True).head(5)
            if not top.empty:
                common = ", ".join([f"{idx} ({val})" for idx, val in top.items()])
                insights.append(
                    ExploreInsight(
                        id=str(uuid4()),
                        type="distribution",
                        title=f"Common values in {c}",
                        description=f"`{c}` has about {nunique} distinct values. Most common: {common}.",
                        chart_suggestion=ChartConfig(
                            id=str(uuid4()),
                            chart_type="bar",
                            x=c,
                            aggregation="count",
                            description=f"Top values of {c}",
                        ),
                    )
                )
                break

    # Correlations (numeric pairs)
    if num.shape[1] >= 2:
        corr = num.corr(numeric_only=True).abs()
        pairs = []
        cols = corr.columns.tolist()
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                v = float(corr.iloc[i, j])
                pairs.append((v, cols[i], cols[j]))
        pairs.sort(reverse=True, key=lambda x: x[0])
        top = [(v, a, b) for (v, a, b) in pairs if v >= 0.6][:3]
        for v, a, b in top:
            insights.append(
                ExploreInsight(
                    id=str(uuid4()),
                    type="correlation",
                    title=f"{a} and {b} move together",
                    description=(
                        f"In the sample, `{a}` and `{b}` are fairly correlated (|r|≈{v:.2f}). "
                        "This can hint at redundancy or a meaningful relationship."
                    ),
                    chart_suggestion=ChartConfig(
                        id=str(uuid4()),
                        chart_type="scatter",
                        x=a,
                        y=b,
                        description=f"{a} vs {b}",
                    ),
                )
            )

    if not insights:
        insights.append(
            ExploreInsight(
                id=str(uuid4()),
                type="summary_stats",
                title="Nothing unusual found (quick check)",
                description="A quick sample-based scan didn’t find obvious issues. You can still explore distributions and relationships visually.",
                chart_suggestion=None,
            )
        )

    return insights


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

