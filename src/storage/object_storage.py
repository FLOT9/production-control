from datetime import timedelta
from io import BytesIO

from minio import Minio
from urllib3 import PoolManager, Timeout

from src.core.config import settings


class ObjectStorage:
    def __init__(self, client: Minio, public_client: Minio) -> None:
        self.client = client
        self.public_client = public_client

    def upload(
        self, bucket: str, object_name: str, data: bytes, content_type: str
    ) -> None:
        self.client.put_object(
            bucket, object_name, BytesIO(data), len(data), content_type=content_type
        )

    def download(self, bucket: str, object_name: str) -> bytes:
        response = self.client.get_object(bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def download_url(
        self, bucket: str, object_name: str, expires: timedelta = timedelta(minutes=15)
    ) -> str:
        return self.public_client.presigned_get_object(
            bucket, object_name, expires=expires
        )

    def check_exists(self, bucket: str, object_name: str) -> None:
        self.client.stat_object(bucket, object_name)


def create_object_storage() -> ObjectStorage:
    def client(endpoint: str) -> Minio:
        return Minio(
            endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=settings.minio_secure,
            region="us-east-1",
            http_client=PoolManager(timeout=Timeout(connect=2, read=10), retries=False),
        )

    return ObjectStorage(
        client(settings.minio_endpoint), client(settings.minio_public_endpoint)
    )
