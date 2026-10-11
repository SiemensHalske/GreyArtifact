from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Iterator

import boto3
from botocore.exceptions import ClientError
from flask import current_app


class ArtifactTooLarge(ValueError):
    pass


class ArtifactStorageUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredObject:
    sha256: str
    storage_key: str
    byte_size: int
    created: bool


class S3ArtifactStorage:
    """S3-compatible, content-addressed storage with bounded streaming input."""

    def __init__(self, client, bucket: str, max_bytes: int):
        self.client = client
        self.bucket = bucket
        self.max_bytes = max_bytes

    def store(self, source: BinaryIO, media_type: str | None = None) -> StoredObject:
        digest = sha256()
        size = 0
        with SpooledTemporaryFile(max_size=min(self.max_bytes, 8 * 1024 * 1024)) as spool:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > self.max_bytes:
                    raise ArtifactTooLarge(
                        f"Artifact exceeds the {self.max_bytes}-byte upload limit."
                    )
                digest.update(chunk)
                spool.write(chunk)

            hex_digest = digest.hexdigest()
            key = f"sha256/{hex_digest[:2]}/{hex_digest}"
            try:
                self.client.head_object(Bucket=self.bucket, Key=key)
                return StoredObject(hex_digest, key, size, False)
            except ClientError as exc:
                status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                code = exc.response.get("Error", {}).get("Code")
                if status != 404 and code not in {"404", "NoSuchKey", "NotFound"}:
                    raise ArtifactStorageUnavailable("Artifact lookup failed.") from exc

            spool.seek(0)
            put_args = {
                "Bucket": self.bucket,
                "Key": key,
                "Body": spool,
                "ContentLength": size,
                "IfNoneMatch": "*",
            }
            if media_type:
                put_args["ContentType"] = media_type
            try:
                self.client.put_object(**put_args)
                created = True
            except ClientError as exc:
                status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                code = exc.response.get("Error", {}).get("Code")
                if status == 412 or code in {"PreconditionFailed", "ConditionalRequestConflict"}:
                    created = False
                else:
                    raise ArtifactStorageUnavailable("Artifact upload failed.") from exc
            return StoredObject(hex_digest, key, size, created)

    def iter_bytes(self, storage_key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=storage_key)["Body"]
        except ClientError as exc:
            raise ArtifactStorageUnavailable("Artifact download failed.") from exc
        try:
            while True:
                chunk = body.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()


def get_artifact_storage() -> S3ArtifactStorage:
    configured = current_app.extensions.get("artifact_storage")
    if configured is not None:
        return configured

    required = ("S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY")
    missing = [name for name in required if not current_app.config.get(name)]
    if missing:
        raise ArtifactStorageUnavailable(
            "Artifact storage is not configured: " + ", ".join(missing)
        )
    client = boto3.client(
        "s3",
        endpoint_url=current_app.config["S3_ENDPOINT_URL"],
        aws_access_key_id=current_app.config["S3_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["S3_SECRET_KEY"],
        region_name=current_app.config.get("S3_REGION", "us-east-1"),
        use_ssl=current_app.config.get("S3_USE_SSL", False),
    )
    storage = S3ArtifactStorage(
        client,
        current_app.config["S3_BUCKET"],
        current_app.config["MAX_ARTIFACT_BYTES"],
    )
    current_app.extensions["artifact_storage"] = storage
    return storage
