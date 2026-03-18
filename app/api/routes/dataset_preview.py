from __future__ import annotations

import json
import math

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.deps import get_session
from app.models import Dataset
from app.services.storage import S3Storage


router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _safe_user_error(message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


def _delimiter_from_key(key: str) -> str:
    lk = key.lower()
    if lk.endswith(".tsv"):
        return "\t"
    return ","


@router.get("/{dataset_id}/preview")
def preview_dataset(
    dataset_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> dict:
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        storage = S3Storage()
    except RuntimeError:
        raise _safe_user_error("File storage isn't configured yet. Please set up S3 and try again.", status_code=503)

    delimiter = _delimiter_from_key(ds.s3_key)

    skip = (page - 1) * page_size
    try:
        body = storage.get_object_stream(ds.s3_key)
        # Note: skiprows uses line numbers; this is a pragmatic "slice" for typical CSVs.
        df = pd.read_csv(body, sep=delimiter, skiprows=range(1, skip + 1), nrows=page_size)
    except Exception:
        raise _safe_user_error("We couldn't preview this dataset. The file may be malformed or not a CSV.")
    finally:
        try:
            body.close()
        except Exception:
            pass

    columns = [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns]
    rows = df.to_dict(orient="records")

    schema = None
    if ds.schema_json:
        try:
            schema = json.loads(ds.schema_json)
        except Exception:
            schema = None

    total = ds.row_count
    total_pages = None
    if isinstance(total, int) and total >= 0:
        total_pages = max(1, math.ceil(total / page_size))

    return {
        "dataset_id": ds.id,
        "s3_key": ds.s3_key,
        "page": page,
        "page_size": page_size,
        "total_rows_approx": total,
        "total_pages_approx": total_pages,
        "columns": columns,
        "rows": rows,
        "schema": schema,
    }

