"""Storage abstraction supporting local development and cloud object storage.

Enforces clear physical separation between:
1. RAW_SOURCE: immutable source satellite scenes and climate datasets.
2. INTERMEDIATE_ARTIFACT: temporary tiled COG chips, masked rasters, and cache files.
3. FINAL_EVIDENCE: signed evidence bundles, audit reports, CSV/PDF deliverables.
4. APPLICATION_METADATA: job states, case snapshots, cryptographic hashes.

Configurable across deployment profiles:
- development: Local filesystem storage under data/
- testing: Isolated temporary local filesystem
- production: S3-compatible cloud object storage (AWS S3, MinIO, Cloudflare R2)

Preserves cryptographic SHA-256 checksums, dataset versions, and provenance metadata.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

S3_CONNECT_TIMEOUT_S = 5
S3_READ_TIMEOUT_S = 30
S3_MAX_ATTEMPTS = 3
"""S3 call limits (#48)."""


class StorageTier(StrEnum):
    """Hierarchical evidence and data separation tiers."""

    RAW_SOURCE = "raw_source"
    INTERMEDIATE_ARTIFACT = "intermediate_artifact"
    FINAL_EVIDENCE = "final_evidence"
    APPLICATION_METADATA = "application_metadata"


@dataclass(frozen=True)
class StorageObjectMetadata:
    """Cryptographic and lineage metadata for a stored artifact."""

    key: str
    tier: StorageTier
    sha256: str
    size_bytes: int
    content_type: str
    created_at: str
    custom_metadata: dict[str, Any] = field(default_factory=dict)


class StorageBackend(Protocol):
    """Abstract interface for file and object persistence."""

    def put_bytes(
        self,
        tier: StorageTier,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: Mapping[str, Any] | None = None,
    ) -> StorageObjectMetadata:
        """Store bytes under a tier and key with cryptographic integrity."""
        ...

    def get_bytes(self, tier: StorageTier, key: str) -> bytes:
        """Retrieve stored bytes. Raises FileNotFoundError if missing."""
        ...

    def exists(self, tier: StorageTier, key: str) -> bool:
        """Check if an object exists in the specified tier."""
        ...

    def delete(self, tier: StorageTier, key: str) -> bool:
        """Delete an object. Returns True if deleted, False if not found."""
        ...

    def list_keys(self, tier: StorageTier, prefix: str = "") -> list[str]:
        """List object keys under a tier and optional prefix."""
        ...

    def get_uri(self, tier: StorageTier, key: str) -> str:
        """Return canonical URI (e.g. file:// or s3://)."""
        ...


class LocalStorageBackend:
    """Local filesystem storage backend with tier subdirectory separation."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir).resolve()
        self._tier_dirs = {
            StorageTier.RAW_SOURCE: self.base_dir / "raw",
            StorageTier.INTERMEDIATE_ARTIFACT: self.base_dir / "interim",
            StorageTier.FINAL_EVIDENCE: self.base_dir / "processed",
            StorageTier.APPLICATION_METADATA: self.base_dir / "metadata",
        }
        for d in self._tier_dirs.values():
            d.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, tier: StorageTier, key: str) -> Path:
        clean_key = key.lstrip("/\\").replace("..", "_")
        target_dir = self._tier_dirs[tier]
        return target_dir / clean_key

    def put_bytes(
        self,
        tier: StorageTier,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: Mapping[str, Any] | None = None,
    ) -> StorageObjectMetadata:
        path = self._resolve_path(tier, key)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write via temporary file
        temp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}")
        temp_path.write_bytes(data)
        temp_path.replace(path)

        sha256 = hashlib.sha256(data).hexdigest()
        meta = StorageObjectMetadata(
            key=key,
            tier=tier,
            sha256=sha256,
            size_bytes=len(data),
            content_type=content_type,
            created_at=str(path.stat().st_mtime),
            custom_metadata=dict(metadata or {}),
        )

        meta_path = path.with_suffix(f"{path.suffix}.meta.json")
        meta_dict = {
            "key": meta.key,
            "tier": meta.tier.value,
            "sha256": meta.sha256,
            "size_bytes": meta.size_bytes,
            "content_type": meta.content_type,
            "created_at": meta.created_at,
            "custom_metadata": meta.custom_metadata,
        }
        meta_path.write_text(json.dumps(meta_dict, indent=2), encoding="utf-8")
        return meta

    def get_bytes(self, tier: StorageTier, key: str) -> bytes:
        path = self._resolve_path(tier, key)
        if not path.is_file():
            raise FileNotFoundError(f"Object not found in tier {tier.value}: {key}")
        return path.read_bytes()

    def exists(self, tier: StorageTier, key: str) -> bool:
        path = self._resolve_path(tier, key)
        return path.is_file()

    def delete(self, tier: StorageTier, key: str) -> bool:
        path = self._resolve_path(tier, key)
        meta_path = path.with_suffix(f"{path.suffix}.meta.json")
        deleted = False
        if path.is_file():
            path.unlink()
            deleted = True
        if meta_path.is_file():
            meta_path.unlink()
        return deleted

    def list_keys(self, tier: StorageTier, prefix: str = "") -> list[str]:
        target_dir = self._tier_dirs[tier]
        keys = []
        for p in target_dir.rglob("*"):
            if p.is_file() and not p.name.endswith(".meta.json") and ".tmp." not in p.name:
                rel = str(p.relative_to(target_dir)).replace("\\", "/")
                if rel.startswith(prefix):
                    keys.append(rel)
        return sorted(keys)

    def get_uri(self, tier: StorageTier, key: str) -> str:
        path = self._resolve_path(tier, key)
        return path.as_uri()


class S3StorageBackend:
    """Production S3-compatible cloud object storage backend.

    Works with AWS S3, Cloudflare R2, MinIO, or Google Cloud Storage.
    """

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region_name: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.region_name = region_name
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key

    def _get_client(self) -> Any:
        try:
            import boto3
        except ImportError as exc:
            raise ImportError(
                "S3StorageBackend requires 'boto3': pip install 'groundtruth[production]'"
            ) from exc

        from botocore.config import Config

        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region_name,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            # Explicit, not botocore's implicit 60 s (#48): 5 s to connect, 30 s to read, and
            # three attempts in the standard retry mode.
            config=Config(
                connect_timeout=S3_CONNECT_TIMEOUT_S,
                read_timeout=S3_READ_TIMEOUT_S,
                retries={"max_attempts": S3_MAX_ATTEMPTS, "mode": "standard"},
            ),
        )

    def _tier_prefix(self, tier: StorageTier, key: str) -> str:
        clean_key = key.lstrip("/")
        return f"{tier.value}/{clean_key}"

    def put_bytes(
        self,
        tier: StorageTier,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: Mapping[str, Any] | None = None,
    ) -> StorageObjectMetadata:
        client = self._get_client()
        s3_key = self._tier_prefix(tier, key)
        sha256 = hashlib.sha256(data).hexdigest()

        s3_meta = {
            "sha256": sha256,
            "tier": tier.value,
        }
        if metadata:
            for k, v in metadata.items():
                s3_meta[f"gt_{k}"] = str(v)

        client.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=data,
            ContentType=content_type,
            Metadata=s3_meta,
        )

        return StorageObjectMetadata(
            key=key,
            tier=tier,
            sha256=sha256,
            size_bytes=len(data),
            content_type=content_type,
            created_at="now",
            custom_metadata=dict(metadata or {}),
        )

    def get_bytes(self, tier: StorageTier, key: str) -> bytes:
        client = self._get_client()
        s3_key = self._tier_prefix(tier, key)
        try:
            resp = client.get_object(Bucket=self.bucket, Key=s3_key)
            return resp["Body"].read()
        except Exception as exc:
            raise FileNotFoundError(f"S3 object not found: s3://{self.bucket}/{s3_key}") from exc

    def exists(self, tier: StorageTier, key: str) -> bool:
        client = self._get_client()
        s3_key = self._tier_prefix(tier, key)
        try:
            client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception:
            return False

    def delete(self, tier: StorageTier, key: str) -> bool:
        client = self._get_client()
        s3_key = self._tier_prefix(tier, key)
        try:
            client.delete_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception:
            return False

    def list_keys(self, tier: StorageTier, prefix: str = "") -> list[str]:
        client = self._get_client()
        s3_prefix = self._tier_prefix(tier, prefix)
        paginator = client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=s3_prefix):
            for obj in page.get("Contents", []):
                full_key = obj["Key"]
                tier_pfx = f"{tier.value}/"
                if full_key.startswith(tier_pfx):
                    keys.append(full_key[len(tier_pfx) :])
        return sorted(keys)

    def get_uri(self, tier: StorageTier, key: str) -> str:
        s3_key = self._tier_prefix(tier, key)
        return f"s3://{self.bucket}/{s3_key}"


def get_storage_backend(
    *,
    profile: str | None = None,
    base_dir: Path | str | None = None,
) -> StorageBackend:
    """Factory creating the appropriate storage backend based on environment configuration.

    Profiles:
    - 'development': Local filesystem under data/
    - 'testing': Isolated temp directory
    - 'production': S3 object storage (if configured), otherwise local fallback
    """
    profile_str = (profile or os.environ.get("DEPLOYMENT_PROFILE") or "development").lower()
    backend_type = os.environ.get("STORAGE_BACKEND", "").lower()

    if backend_type == "s3" or (profile_str == "production" and os.environ.get("S3_BUCKET")):
        bucket = os.environ.get("S3_BUCKET", "groundtruth-production-evidence")
        endpoint = os.environ.get("S3_ENDPOINT_URL")
        region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        return S3StorageBackend(
            bucket=bucket,
            endpoint_url=endpoint,
            region_name=region,
            access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        )

    # Default to LocalStorageBackend
    if base_dir is not None:
        target_dir = Path(base_dir)
    else:
        repo_root = Path(__file__).resolve().parents[5]
        target_dir = repo_root / "data"

    return LocalStorageBackend(target_dir)


__all__ = [
    "LocalStorageBackend",
    "S3StorageBackend",
    "StorageBackend",
    "StorageObjectMetadata",
    "StorageTier",
    "get_storage_backend",
]
