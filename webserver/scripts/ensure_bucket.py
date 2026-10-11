#!/usr/bin/env python3
import os
import time

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError


def main() -> None:
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name=os.environ.get("S3_REGION", "us-east-1"),
    )
    bucket = os.environ["S3_BUCKET"]
    for attempt in range(30):
        try:
            client.head_bucket(Bucket=bucket)
            return
        except EndpointConnectionError:
            if attempt == 29:
                raise
            time.sleep(1)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            code = exc.response.get("Error", {}).get("Code")
            if status in {403, 404} or code in {"403", "404", "NoSuchBucket"}:
                client.create_bucket(Bucket=bucket)
                return
            raise


if __name__ == "__main__":
    main()
