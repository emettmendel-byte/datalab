from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import boto3

from app.core.config import settings


@dataclass(frozen=True)
class PutObjectResult:
    bucket: str
    key: str


class S3Storage:
    def __init__(self) -> None:
        self._bucket = settings.s3_bucket
        self._use_local = not bool(self._bucket)
        self._base_local_dir = Path(settings.local_storage_dir).resolve()
        self._client = None

        if self._use_local:
            self._base_local_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._client = boto3.client(
                "s3",
                region_name=settings.s3_region,
                endpoint_url=settings.s3_endpoint_url,
            )

    def put_fileobj(self, fileobj: BinaryIO, key: str, content_type: str | None = None) -> PutObjectResult:
        if self._use_local:
            path = self._to_local_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            fileobj.seek(0)
            with path.open("wb") as f:
                while True:
                    chunk = fileobj.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            return PutObjectResult(bucket="local", key=key)

        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        self._client.upload_fileobj(fileobj, self._bucket, key, ExtraArgs=extra or None)
        return PutObjectResult(bucket=self._bucket, key=key)

    def get_object_stream(self, key: str):
        """
        Returns the underlying boto3 StreamingBody.
        Caller is responsible for reading/closing it.
        """
        if self._use_local:
            path = self._to_local_path(key)
            if not path.exists():
                raise FileNotFoundError(f"Local storage key not found: {key}")
            return path.open("rb")

        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"]

    def head_object(self, key: str) -> dict:
        if self._use_local:
            path = self._to_local_path(key)
            if not path.exists():
                raise FileNotFoundError(f"Local storage key not found: {key}")
            stat = path.stat()
            return {"ContentLength": stat.st_size}
        return self._client.head_object(Bucket=self._bucket, Key=key)

    def _to_local_path(self, key: str) -> Path:
        normalized = key.lstrip("/").replace("..", "_")
        return self._base_local_dir / normalized

