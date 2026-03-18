from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.models import Dataset
from app.schemas import CleaningOperationType, CleaningStep
from app.services.storage import S3Storage


_CLEAN_KEY_RE = re.compile(r"_clean_v(?P<v>\d+)\.csv$", re.IGNORECASE)


@dataclass(frozen=True)
class CleaningResult:
    new_s3_key: str
    schema_json: str
    row_count: int | None
    preview_rows: list[dict]
    code_snippets: list[str]


def apply_cleaning_steps(dataset: Dataset, steps: list[CleaningStep]) -> CleaningResult:
    """
    Safe, explicit, whitelisted cleaning. Ignores step.generated_code.
    Reads CSV from S3 (sampling if large), applies steps, writes cleaned CSV back to S3.
    """
    storage = S3Storage()
    delimiter = "\t" if dataset.s3_key.lower().endswith(".tsv") else ","

    nrows = None
    if isinstance(dataset.row_count, int) and dataset.row_count > 1_000_000:
        # Respect time budget: operate on a manageable sample.
        nrows = 200_000

    body = storage.get_object_stream(dataset.s3_key)
    try:
        df = pd.read_csv(body, sep=delimiter, nrows=nrows)
    except Exception as e:
        raise ValueError("We couldn't load this dataset for cleaning. Please check that it's a valid CSV.") from e
    finally:
        try:
            body.close()
        except Exception:
            pass

    code_snippets: list[str] = []
    for step in steps:
        snippet = _apply_step_inplace(df, step)
        code_snippets.append(snippet)

    new_key = _next_clean_key(dataset.s3_key)

    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    storage.put_fileobj(buf, key=new_key, content_type="text/csv")

    columns_meta = [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns]
    schema_json = json.dumps({"columns": columns_meta})

    if nrows is not None:
        row_count = dataset.row_count
    else:
        row_count = int(df.shape[0])

    preview_rows = df.head(100).to_dict(orient="records")

    return CleaningResult(
        new_s3_key=new_key,
        schema_json=schema_json,
        row_count=row_count,
        preview_rows=preview_rows,
        code_snippets=code_snippets,
    )


def _next_clean_key(original_key: str) -> str:
    key = original_key
    if not key.lower().endswith((".csv", ".tsv", ".txt")):
        key = f"{key}.csv"

    m = _CLEAN_KEY_RE.search(key)
    if m:
        v = int(m.group("v"))
        return _CLEAN_KEY_RE.sub(f"_clean_v{v + 1}.csv", key)

    if key.lower().endswith(".csv"):
        return key[:-4] + "_clean_v1.csv"
    if key.lower().endswith(".tsv"):
        return key[:-4] + "_clean_v1.csv"
    if key.lower().endswith(".txt"):
        return key[:-4] + "_clean_v1.csv"
    return key + "_clean_v1.csv"


def _apply_step_inplace(df: pd.DataFrame, step: CleaningStep) -> str:
    op = step.operation_type
    p: dict[str, Any] = step.parameters or {}

    if op == CleaningOperationType.DROP_COLUMNS:
        cols = list(p.get("columns") or [])
        df.drop(columns=[c for c in cols if c in df.columns], inplace=True, errors="ignore")
        return f"df.drop(columns={cols!r}, inplace=True, errors='ignore')"

    if op == CleaningOperationType.DROP_ROWS_WITH_MISSING:
        cols = p.get("columns")
        subset = [c for c in (cols or []) if c in df.columns] if cols else None
        before = len(df)
        df.dropna(subset=subset, inplace=True)
        return f"df.dropna(subset={subset!r}, inplace=True)  # {before} -> {len(df)} rows"

    if op == CleaningOperationType.FILL_MISSING:
        strategy = str(p.get("strategy") or "constant").lower()
        value = p.get("value", 0)
        cols = p.get("columns")
        target_cols = [c for c in (cols or df.columns.tolist()) if c in df.columns]
        for c in target_cols:
            if strategy == "mean" and pd.api.types.is_numeric_dtype(df[c]):
                fill = float(df[c].mean())
            elif strategy == "median" and pd.api.types.is_numeric_dtype(df[c]):
                fill = float(df[c].median())
            elif strategy == "mode":
                mode = df[c].mode(dropna=True)
                fill = mode.iloc[0] if not mode.empty else value
            else:
                fill = value
            df[c] = df[c].fillna(fill)
        return f"# fill_missing strategy={strategy!r}, columns={target_cols!r}"

    if op == CleaningOperationType.CAST_TYPE:
        col = p.get("column")
        dtype = str(p.get("dtype") or "")
        if not col or col not in df.columns:
            return "# cast_type skipped (missing column)"
        if dtype in {"int", "int64"}:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        elif dtype in {"float", "float64"}:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
        elif dtype in {"str", "string"}:
            df[col] = df[col].astype("string")
        elif dtype == "category":
            df[col] = df[col].astype("category")
        elif dtype in {"datetime", "datetime64", "datetime64[ns]"}:
            df[col] = pd.to_datetime(df[col], errors="coerce")
        else:
            df[col] = df[col].astype("string")
        return f"df[{col!r}] = df[{col!r}].astype({dtype!r})"

    if op == CleaningOperationType.FILTER_ROWS:
        col = p.get("column")
        op_str = str(p.get("op") or "")
        value = p.get("value")
        if not col or col not in df.columns:
            return "# filter_rows skipped (missing column)"
        before = len(df)
        s = df[col]

        if op_str in {"==", "!=", ">", ">=", "<", "<="}:
            try:
                if op_str == "==":
                    mask = s == value
                elif op_str == "!=":
                    mask = s != value
                elif op_str == ">":
                    mask = s > value
                elif op_str == ">=":
                    mask = s >= value
                elif op_str == "<":
                    mask = s < value
                else:
                    mask = s <= value
            except Exception:
                return "# filter_rows skipped (comparison failed)"
        elif op_str == "in":
            vals = list(value or [])
            mask = s.isin(vals)
        elif op_str == "not_in":
            vals = list(value or [])
            mask = ~s.isin(vals)
        elif op_str == "contains":
            needle = "" if value is None else str(value)
            mask = s.astype("string").str.contains(needle, na=False)
        else:
            return "# filter_rows skipped (unsupported op)"

        df.drop(index=df.index[~mask], inplace=True)
        df.reset_index(drop=True, inplace=True)
        return f"# filter_rows {col} {op_str} {value!r}  # {before} -> {len(df)} rows"

    if op == CleaningOperationType.DEDUP_ROWS:
        subset = p.get("columns")
        subset_cols = [c for c in (subset or []) if c in df.columns] if subset else None
        before = len(df)
        df.drop_duplicates(subset=subset_cols, inplace=True)
        df.reset_index(drop=True, inplace=True)
        return f"df.drop_duplicates(subset={subset_cols!r}, inplace=True)  # {before} -> {len(df)} rows"

    if op == CleaningOperationType.STANDARDIZE_CATEGORIES:
        col = p.get("column")
        if not col or col not in df.columns:
            return "# standardize_categories skipped (missing column)"
        strip = bool(p.get("strip", True))
        lower = bool(p.get("lower", True))
        mapping = p.get("mapping") or {}
        s = df[col].astype("string")
        if strip:
            s = s.str.strip()
        if lower:
            s = s.str.lower()
        if isinstance(mapping, dict) and mapping:
            s = s.replace(mapping)
        df[col] = s
        return f"# standardize_categories column={col!r}, strip={strip}, lower={lower}, mapping_keys={list(mapping)[:5]!r}"

    if op == CleaningOperationType.PARSE_DATES:
        col = p.get("column")
        if not col or col not in df.columns:
            return "# parse_dates skipped (missing column)"
        fmt = p.get("format")
        df[col] = pd.to_datetime(df[col], errors="coerce", format=fmt)
        return f"df[{col!r}] = pd.to_datetime(df[{col!r}], errors='coerce', format={fmt!r})"

    return "# unknown operation skipped"


class CleaningService:
    """
    Placeholder for whitelisted pandas operations.
    Implement as your UI/agent contract solidifies.
    """

    pass

