from __future__ import annotations

from dataclasses import dataclass
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
        if not self._bucket:
            raise RuntimeError("S3_BUCKET is not configured.")

        self._client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
        )

    def put_fileobj(self, fileobj: BinaryIO, key: str, content_type: str | None = None) -> PutObjectResult:
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
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"]

    def head_object(self, key: str) -> dict:
        return self._client.head_object(Bucket=self._bucket, Key=key)

