"""Object storage abstraction (local disk or S3-compatible) with signed, short-lived download URLs."""
from __future__ import annotations

import os
import re
import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import get_settings
from app.core.crypto import sign_payload, verify_payload


class Storage(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...
    @abstractmethod
    def get(self, key: str) -> bytes: ...
    @abstractmethod
    def delete(self, key: str) -> None: ...
    @abstractmethod
    def delete_prefix(self, prefix: str) -> int: ...


_SAFE = re.compile(r"^[A-Za-z0-9/_\-.]+$")


def _check_key(key: str) -> str:
    if not _SAFE.match(key) or ".." in key or key.startswith("/"):
        raise ValueError("invalid storage key")
    return key


class LocalStorage(Storage):
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / _check_key(key)).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def put(self, key, data, content_type="application/octet-stream"):
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)

    def get(self, key):
        return self._path(key).read_bytes()

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix):
        p = self._path(prefix.rstrip("/"))
        if not p.exists():
            return 0
        n = sum(1 for _ in p.rglob("*") if _.is_file())
        shutil.rmtree(p, ignore_errors=True)
        return n


class S3Storage(Storage):  # pragma: no cover - exercised against MinIO/S3 in staging
    def __init__(self):
        import boto3

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client("s3", endpoint_url=s.s3_endpoint_url, region_name=s.s3_region,
                                   aws_access_key_id=s.s3_access_key, aws_secret_access_key=s.s3_secret_key)

    def put(self, key, data, content_type="application/octet-stream"):
        self.client.put_object(Bucket=self.bucket, Key=_check_key(key), Body=data, ContentType=content_type, ServerSideEncryption="AES256")

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=_check_key(key))["Body"].read()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=_check_key(key))

    def delete_prefix(self, prefix):
        n = 0
        pag = self.client.get_paginator("list_objects_v2")
        for page in pag.paginate(Bucket=self.bucket, Prefix=_check_key(prefix)):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if keys:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})
                n += len(keys)
        return n


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3Storage() if s.storage_backend == "s3" else LocalStorage(s.storage_local_path)
    return _storage


def reset_storage() -> None:
    global _storage
    _storage = None


def new_key(user_id: uuid.UUID, kind: str, ext: str) -> str:
    ext = re.sub(r"[^a-z0-9]", "", ext.lower())[:8] or "bin"
    return f"u/{user_id}/{kind}/{uuid.uuid4().hex}.{ext}"


def signed_download_token(user_id: uuid.UUID, key: str, filename: str, content_type: str) -> str:
    return sign_payload({"u": str(user_id), "k": key, "f": filename, "t": content_type}, get_settings().signed_url_seconds, "download")


def verify_download_token(token: str) -> dict | None:
    body = verify_payload(token, "download")
    if not body or not body["k"].startswith(f"u/{body['u']}/"):
        return None
    return body
