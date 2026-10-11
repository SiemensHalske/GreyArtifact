import io
import os
import unittest
from pathlib import Path
from uuid import uuid4

import boto3
import psycopg

from app.services.artifact_storage import S3ArtifactStorage


@unittest.skipUnless(
    os.environ.get("GREYARTIFACT_INTEGRATION") == "1",
    "set GREYARTIFACT_INTEGRATION=1 for PostgreSQL/MinIO tests",
)
class PostgresMinioIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_connection = {
            "host": os.environ["INTEGRATION_DB_HOST"],
            "port": int(os.environ["INTEGRATION_DB_PORT"]),
            "dbname": os.environ["INTEGRATION_DB_NAME"],
            "user": os.environ["INTEGRATION_DB_USER"],
            "password": os.environ["INTEGRATION_DB_PASSWORD"],
        }
        cls.s3 = boto3.client(
            "s3",
            endpoint_url=os.environ["INTEGRATION_S3_ENDPOINT"],
            aws_access_key_id=os.environ["INTEGRATION_S3_ACCESS_KEY"],
            aws_secret_access_key=os.environ["INTEGRATION_S3_SECRET_KEY"],
            region_name="us-east-1",
        )
        cls.bucket = os.environ["INTEGRATION_S3_BUCKET"]

    def test_clean_install_contains_private_demo_schema(self):
        with psycopg.connect(**self.db_connection) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT to_regclass('recon.engagements'), "
                    "to_regclass('recon.recon_runs'), "
                    "to_regclass('recon.recon_run_steps')"
                )
                self.assertTrue(all(cursor.fetchone()))
                cursor.execute(
                    """
                    SELECT r.code
                    FROM recon.roles AS r
                    JOIN recon.role_permissions AS rp USING (role_id)
                    JOIN recon.permissions AS p USING (permission_id)
                    WHERE p.code = 'recon.execute'
                    ORDER BY r.code
                    """
                )
                self.assertEqual(cursor.fetchall(), [("owner",)])

    def test_minio_content_addressing_and_deduplication(self):
        storage = S3ArtifactStorage(self.s3, self.bucket, 1024)
        payload = f"fixture-evidence-{uuid4()}".encode()
        first = storage.store(io.BytesIO(payload), "text/plain")
        second = storage.store(io.BytesIO(payload), "text/plain")
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.storage_key, second.storage_key)
        self.assertEqual(b"".join(storage.iter_bytes(first.storage_key)), payload)

    def test_upgrade_from_004_to_005(self):
        database_name = f"ga_upgrade_{uuid4().hex}"
        admin = dict(self.db_connection)
        admin["dbname"] = "postgres"
        root = Path(__file__).resolve().parents[2]
        try:
            with psycopg.connect(**admin, autocommit=True) as connection:
                connection.execute(f'CREATE DATABASE "{database_name}"')
            upgrade_config = dict(self.db_connection)
            upgrade_config["dbname"] = database_name
            with psycopg.connect(**upgrade_config, autocommit=True) as connection:
                for number in range(1, 5):
                    migration = next(
                        (root / "database" / "migrations").glob(f"{number:03d}_*.sql")
                    )
                    connection.execute(migration.read_text(encoding="utf-8"))
                self.assertIsNone(
                    connection.execute(
                        "SELECT to_regclass('recon.engagements')"
                    ).fetchone()[0]
                )
                migration = next(
                    (root / "database" / "migrations").glob("005_*.sql")
                )
                connection.execute(migration.read_text(encoding="utf-8"))
                self.assertIsNotNone(
                    connection.execute(
                        "SELECT to_regclass('recon.engagements')"
                    ).fetchone()[0]
                )
        finally:
            with psycopg.connect(**admin, autocommit=True) as connection:
                connection.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s",
                    (database_name,),
                )
                connection.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
