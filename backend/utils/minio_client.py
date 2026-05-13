"""
AgroSight AI — MinIO Object Storage Client
═════════════════════════════════════════════
Production-ready wrapper for MinIO (S3-compatible) object storage.
Handles uploads, downloads, and presigned URLs for crop images,
voice notes, model backups, and feedback datasets.
"""

import os
import io
import base64
import re
import logging
from typing import Optional, BinaryIO, Union
from datetime import timedelta

try:
    from minio import Minio
    from minio.error import S3Error
    HAS_MINIO = True
except ImportError:
    HAS_MINIO = False
    Minio = None
    S3Error = Exception

import config as app_config

logger = logging.getLogger(__name__)


class MinioStorage:
    """MinIO object storage client with bucket auto-creation."""

    _instance: Optional['MinioStorage'] = None

    def __new__(cls) -> 'MinioStorage':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._client = None
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        if not HAS_MINIO or not app_config.MINIO_ENABLED:
            logger.info("MinIO storage disabled (MINIO_ENABLED=false or minio SDK not installed)")
            return

        endpoint = app_config.MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
        try:
            self._client = Minio(
                endpoint,
                access_key=app_config.MINIO_ACCESS_KEY,
                secret_key=app_config.MINIO_SECRET_KEY,
                secure=app_config.MINIO_SECURE,
            )
            self._ensure_buckets()
            logger.info(f"MinIO client connected to {endpoint}")
        except Exception as e:
            logger.error(f"Failed to connect to MinIO at {endpoint}: {e}")
            self._client = None

    def _ensure_buckets(self):
        """Create required buckets if they don't exist."""
        buckets = [
            app_config.MINIO_BUCKET_UPLOADS,
            app_config.MINIO_BUCKET_MODELS,
            app_config.MINIO_BUCKET_DATASETS,
            app_config.MINIO_BUCKET_FEEDBACK,
        ]
        for name in buckets:
            try:
                if not self._client.bucket_exists(name):
                    self._client.make_bucket(name)
                    logger.info(f"Created MinIO bucket: {name}")
            except Exception as e:
                logger.warning(f"Could not create bucket {name}: {e}")

    @property
    def available(self) -> bool:
        return self._client is not None

    def upload_file(
        self,
        bucket: str,
        object_name: str,
        data: Union[bytes, BinaryIO],
        content_type: str = "application/octet-stream",
        length: int = -1,
    ) -> Optional[str]:
        """Upload a file to MinIO. Returns the object name on success."""
        if not self.available:
            return None
        try:
            if isinstance(data, bytes):
                data = io.BytesIO(data)
                length = len(data.getvalue())
            self._client.put_object(
                bucket, object_name, data, length=length, content_type=content_type
            )
            logger.info(f"Uploaded {object_name} to {bucket}")
            return object_name
        except S3Error as e:
            logger.error(f"MinIO upload error for {object_name}: {e}")
            return None

    def upload_base64_image(
        self,
        bucket: str,
        object_name: str,
        base64_data: str,
        content_type: str = "image/jpeg",
    ) -> Optional[str]:
        """Upload a base64-encoded image string to MinIO."""
        try:
            raw = base64.b64decode(base64_data)
            return self.upload_file(bucket, object_name, raw, content_type, len(raw))
        except Exception as e:
            logger.error(f"Base64 decode/upload error: {e}")
            return None

    def get_object(self, bucket: str, object_name: str) -> Optional[bytes]:
        """Download an object from MinIO."""
        if not self.available:
            return None
        try:
            response = self._client.get_object(bucket, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            logger.error(f"MinIO download error for {object_name}: {e}")
            return None

    def get_presigned_url(
        self,
        bucket: str,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> Optional[str]:
        """Generate a presigned GET URL for temporary access."""
        if not self.available:
            return None
        try:
            return self._client.presigned_get_object(bucket, object_name, expires=expires)
        except S3Error as e:
            logger.error(f"MinIO presigned URL error: {e}")
            return None

    def delete_object(self, bucket: str, object_name: str) -> bool:
        """Delete an object from MinIO."""
        if not self.available:
            return False
        try:
            self._client.remove_object(bucket, object_name)
            logger.info(f"Deleted {object_name} from {bucket}")
            return True
        except S3Error as e:
            logger.error(f"MinIO delete error for {object_name}: {e}")
            return False

    def list_objects(self, bucket: str, prefix: str = ""):
        """List objects in a bucket with optional prefix filter."""
        if not self.available:
            return []
        try:
            return list(self._client.list_objects(bucket, prefix=prefix, recursive=True))
        except S3Error as e:
            logger.error(f"MinIO list error: {e}")
            return []


# ── Singleton instance ──
minio_storage = MinioStorage()


def store_upload(image_data_b64: str, filename: str, bucket: Optional[str] = None) -> Optional[str]:
    """Store an uploaded image in MinIO. Returns object name or None."""
    if not minio_storage.available:
        return None
    bucket = bucket or app_config.MINIO_BUCKET_UPLOADS
    object_name = f"uploads/{filename}"
    return minio_storage.upload_base64_image(bucket, object_name, image_data_b64)


def store_feedback_image(image_data_b64: str, filename: str) -> Optional[str]:
    """Store a feedback image in MinIO."""
    if not minio_storage.available:
        return None
    object_name = f"feedback/{filename}"
    return minio_storage.upload_base64_image(
        app_config.MINIO_BUCKET_FEEDBACK, object_name, image_data_b64
    )


def store_model_backup(local_path: str, object_name: str) -> Optional[str]:
    """Upload a model file to MinIO for backup."""
    if not minio_storage.available:
        return None
    try:
        with open(local_path, "rb") as f:
            data = f.read()
        return minio_storage.upload_file(
            app_config.MINIO_BUCKET_MODELS,
            object_name,
            data,
            "application/octet-stream",
            len(data),
        )
    except Exception as e:
        logger.error(f"Model backup upload error: {e}")
        return None
