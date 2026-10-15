#!/usr/bin/env python3
"""Stream the artifact bucket to or from an uncompressed tar archive.

`export` writes every object to standard output; `import` reads such an
archive from standard input. Objects are content-addressed, so import
recomputes each SHA-256 through `S3ArtifactStorage` and rejects members whose
name does not match their content. Connection settings come from the
environment, falling back to the repository-root `.env`.
"""

from __future__ import annotations

import argparse
import os
import sys
import tarfile
from pathlib import Path

import boto3
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "webserver" / "src"))

from app.services.artifact_storage import S3ArtifactStorage  # noqa: E402

# Restores must accept every archived object even if the upload limit shrank.
RESTORE_MAX_BYTES = 10 * 1024**3


def _client_and_bucket():
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    missing = [
        name
        for name in ("S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET")
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError(f"Missing settings: {', '.join(missing)}")
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name=os.environ.get("S3_REGION", "us-east-1"),
    )
    return client, os.environ["S3_BUCKET"]


def export_bucket(client, bucket: str, output) -> int:
    count = 0
    with tarfile.open(fileobj=output, mode="w|") as archive:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            for item in page.get("Contents", []):
                body = client.get_object(Bucket=bucket, Key=item["Key"])["Body"]
                info = tarfile.TarInfo(item["Key"])
                info.size = item["Size"]
                info.mtime = int(item["LastModified"].timestamp())
                archive.addfile(info, body)
                count += 1
    return count


def import_bucket(client, bucket: str, source) -> tuple[int, int]:
    storage = S3ArtifactStorage(client, bucket, RESTORE_MAX_BYTES)
    created = existing = 0
    with tarfile.open(fileobj=source, mode="r|") as archive:
        for member in archive:
            if not member.isfile():
                raise RuntimeError(f"Unexpected archive member type: {member.name}")
            stored = storage.store(archive.extractfile(member))
            if stored.storage_key != member.name:
                raise RuntimeError(
                    f"Content of {member.name} does not match its SHA-256 key."
                )
            if stored.created:
                created += 1
            else:
                existing += 1
    return created, existing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "import"])
    args = parser.parse_args()
    try:
        client, bucket = _client_and_bucket()
        if args.action == "export":
            count = export_bucket(client, bucket, sys.stdout.buffer)
            print(f"Exported {count} objects from {bucket!r}.", file=sys.stderr)
        else:
            created, existing = import_bucket(client, bucket, sys.stdin.buffer)
            print(
                f"Imported into {bucket!r}: {created} new, {existing} already present.",
                file=sys.stderr,
            )
    except RuntimeError as error:
        print(f"Artifact archive {args.action} failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
