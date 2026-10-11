from __future__ import annotations

import io
from hashlib import sha256

from app.services.artifact_storage import ArtifactTooLarge, StoredObject


class InMemoryArtifactStorage:
    def __init__(self, max_bytes=100 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.objects = {}

    def store(self, source, media_type=None):
        output = io.BytesIO()
        digest = sha256()
        size = 0
        while True:
            chunk = source.read(8192)
            if not chunk:
                break
            size += len(chunk)
            if size > self.max_bytes:
                raise ArtifactTooLarge("too large")
            output.write(chunk)
            digest.update(chunk)
        value = digest.hexdigest()
        key = f"sha256/{value[:2]}/{value}"
        created = key not in self.objects
        self.objects.setdefault(key, output.getvalue())
        return StoredObject(value, key, size, created)

    def iter_bytes(self, storage_key, chunk_size=64 * 1024):
        data = self.objects[storage_key]
        for offset in range(0, len(data), chunk_size):
            yield data[offset : offset + chunk_size]
