"""Content-addressed, write-once storage for raw documents.

Keyed by the SHA-256 of the bytes, so re-ingesting the same message is a no-op
and a stored blob can never disagree with the hash we committed to. Writes never
overwrite: if the key exists, the content is already exactly right by
definition, and if it somehow isn't, silently replacing it would destroy the
evidence rather than surface the problem.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from adapters.config import settings


def content_key(data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    # Sharded so a directory listing stays usable at a few hundred thousand
    # documents.
    return f"{digest[:2]}/{digest[2:4]}/{digest}"


class BlobStore(Protocol):
    def put(self, data: bytes) -> str: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


class FilesystemBlobStore:
    """For local development, and for Render with a mounted disk."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        root = self.root.resolve()
        if not str(path).startswith(str(root)):
            raise ValueError(f"blob key escapes the store root: {key!r}")
        return path

    def put(self, data: bytes) -> str:
        key = content_key(data)
        path = self._path(key)
        if path.exists():
            return key
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary name and rename, so a crash mid-write cannot
        # leave a truncated blob sitting under a hash that promises otherwise.
        temp = path.with_suffix(".partial")
        temp.write_bytes(data)
        temp.rename(path)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3BlobStore:
    """S3 or any S3-compatible endpoint — R2, B2, Spaces."""

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region: str = "auto",
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        import boto3

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def put(self, data: bytes) -> str:
        key = content_key(data)
        if not self.exists(key):
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


_store: BlobStore | None = None


def blob_store() -> BlobStore:
    global _store
    if _store is None:
        config = settings()
        if config.uses_s3:
            _store = S3BlobStore(
                config.s3_bucket or "",
                endpoint_url=config.s3_endpoint_url,
                region=config.s3_region,
                access_key=config.aws_access_key_id,
                secret_key=config.aws_secret_access_key,
            )
        else:
            _store = FilesystemBlobStore(config.blob_dir)
    return _store


def reset_blob_store() -> None:
    """Tests point the store somewhere temporary."""
    global _store
    _store = None
