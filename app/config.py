from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "仲裁证据交换服务"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/arbitration_evidence"

    SECRET_KEY: str = "your-secret-key-change-in-production-xxxxxxxxxxxxxxxxxxxx"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    UPLOAD_DIR: str = "./uploads"
    CHUNK_DIR: str = "./uploads/chunks"
    MAX_UPLOAD_SIZE: int = 1024 * 1024 * 1024
    CHUNK_SIZE: int = 1024 * 1024 * 5

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
