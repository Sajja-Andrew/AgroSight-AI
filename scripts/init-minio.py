#!/usr/bin/env python3
"""
AgroSight AI — MinIO Bucket Initialization
═════════════════════════════════════════════
Creates required buckets and sets policies for production.
Run once at container startup (idempotent).
"""

import os
import sys
from minio import Minio
from minio.error import S3Error


MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "agrosight")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "change-me-in-production")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"

BUCKETS = [
    os.environ.get("MINIO_BUCKET_UPLOADS", "uploads"),
    os.environ.get("MINIO_BUCKET_MODELS", "models"),
    os.environ.get("MINIO_BUCKET_DATASETS", "datasets"),
    os.environ.get("MINIO_BUCKET_FEEDBACK", "feedback"),
]


def get_minio_client():
    """Create MinIO client from environment variables."""
    # Strip protocol from endpoint
    endpoint = MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
    return Minio(
        endpoint,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def init_buckets():
    """Create all required buckets with policies."""
    try:
        client = get_minio_client()

        # Check connectivity
        if not client.bucket_exists(BUCKETS[0]):
            print("[init-minio] Connected to MinIO successfully")
        else:
            print("[init-minio] Buckets already initialized")
            return 0

        for bucket_name in BUCKETS:
            if not client.bucket_exists(bucket_name):
                client.make_bucket(bucket_name)
                print(f"[init-minio] Created bucket: {bucket_name}")
            else:
                print(f"[init-minio] Bucket already exists: {bucket_name}")

        # Set bucket policies (uploads and feedback are private,
        # datasets can be read-only for the app)
        policy = """{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": ["arn:aws:s3:::%s/*"]
                }
            ]
        }"""

        # Make datasets bucket readable (for model distribution)
        client.set_bucket_policy(BUCKETS[2], policy % BUCKETS[2])
        print(f"[init-minio] Set public read policy on bucket: {BUCKETS[2]}")

        print("[init-minio] MinIO initialization complete")
        return 0

    except S3Error as e:
        print(f"[init-minio] S3 Error: {e}")
        return 1
    except Exception as e:
        print(f"[init-minio] Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(init_buckets())
