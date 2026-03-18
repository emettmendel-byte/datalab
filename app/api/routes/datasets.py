from __future__ import annotations

import io
import json
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi import File, Form, UploadFile
from sqlmodel import Session, select

from app.deps import get_session
from app.models import Dataset, Project
from app.schemas import DatasetCreate, DatasetRead
from app.services.storage import S3Storage


router = APIRouter(prefix="/api/projects/{project_id}/datasets", tags=["datasets"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTS = {".csv", ".tsv", ".txt"}


def _safe_user_error(message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


def _guess_delimiter(filename: str) -> str:
    name = filename.lower()
    if name.endswith(".tsv"):
        return "\t"
    return ","


def _validate_upload(file: UploadFile) -> tuple[int, str]:
    filename = file.filename or ""
    lower = filename.lower()
    ext = ""
    if "." in lower:
        ext = "." + lower.rsplit(".", 1)[-1]
    if ext and ext not in ALLOWED_EXTS:
        raise _safe_user_error("Please upload a CSV or delimited text file (e.g., .csv, .tsv, .txt).")

    try:
        f = file.file
        f.seek(0, io.SEEK_END)
        size = int(f.tell())
        f.seek(0)
    except Exception:
        size = -1

    if size != -1 and size > MAX_UPLOAD_BYTES:
        raise _safe_user_error("That file is too large. Please upload a file up to 50MB.")

    delimiter = _guess_delimiter(filename)
    return size, delimiter


def _infer_schema_and_preview(storage: S3Storage, s3_key: str, delimiter: str) -> tuple[str, int | None, list[dict], list[dict]]:
    """
    Returns:
      schema_json (string), approximate row_count, preview_rows (<=50), columns_meta
    """
    body = storage.get_object_stream(s3_key)
    try:
        df = pd.read_csv(body, sep=delimiter, nrows=2000)
    except Exception:
        raise _safe_user_error("We couldn't read that file as a table. Please upload a standard CSV (or TSV).")
    finally:
        try:
            body.close()
        except Exception:
            pass

    columns_meta = [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns]
    schema_json = json.dumps({"columns": columns_meta})

    preview_rows = df.head(50).to_dict(orient="records")

    approx_rows: int | None = None
    try:
        body2 = storage.get_object_stream(s3_key)
        line_count = 0
        for chunk in iter(lambda: body2.read(1024 * 1024), b""):
            line_count += chunk.count(b"\n")
        body2.close()
        approx_rows = max(0, line_count - 1)
    except Exception:
        approx_rows = None

    return schema_json, approx_rows, preview_rows, columns_meta


@router.get("", response_model=list[DatasetRead])
def list_datasets(project_id: int, session: Session = Depends(get_session)) -> list[Dataset]:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return list(session.exec(select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.created_at.desc())))


@router.post("", response_model=DatasetRead)
def create_dataset(project_id: int, payload: DatasetCreate, session: Session = Depends(get_session)) -> Dataset:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    ds = Dataset(
        project_id=project_id,
        name=payload.name,
        source_type=payload.source_type,
        s3_key=payload.s3_key,
        schema_json=payload.schema_json,
        row_count=payload.row_count,
    )
    session.add(ds)
    session.commit()
    session.refresh(ds)
    return ds


@router.post("/upload")
def upload_dataset(
    project_id: int,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str | None = Form(None),
    session: Session = Depends(get_session),
) -> dict:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    _size, delimiter = _validate_upload(file)

    if not file.filename:
        raise _safe_user_error("Please choose a file to upload.")

    key = f"projects/{project_id}/datasets/{uuid4()}.csv"

    try:
        storage = S3Storage()
    except RuntimeError:
        raise _safe_user_error("File storage isn't configured yet. Please set up S3 and try again.", status_code=503)

    try:
        file.file.seek(0)
        storage.put_fileobj(file.file, key=key, content_type=file.content_type)
    except Exception:
        raise _safe_user_error("Upload failed. Please try again, or choose a different file.")

    schema_json, row_count, preview_rows, columns_meta = _infer_schema_and_preview(storage, key, delimiter)

    ds = Dataset(
        project_id=project_id,
        name=name,
        source_type="upload",
        s3_key=key,
        schema_json=schema_json,
        row_count=row_count,
    )
    session.add(ds)
    session.commit()
    session.refresh(ds)

    return {
        "dataset": DatasetRead.model_validate(ds),
        "columns": columns_meta,
        "rows": preview_rows,
        "note": description,
    }

