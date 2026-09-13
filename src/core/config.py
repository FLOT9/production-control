from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    debug: bool = False
    celery_broker_url: str
    celery_result_backend: str
    redis_cache_url: str
    work_center_cache_ttl_seconds: int = 60
    minio_endpoint: str = "localhost:9000"
    minio_public_endpoint: str = "localhost:9000"
    minio_root_user: str = "production_control"
    minio_root_password: str = "local-minio-password"
    minio_secure: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
