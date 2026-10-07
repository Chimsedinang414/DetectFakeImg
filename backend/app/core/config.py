"""Application configuration using environment variables."""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    APP_NAME: str = "DetectFakeIMG"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS — cho phép frontend kết nối
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"]

    # Storage
    UPLOAD_DIR: Path = Path("uploads")
    TEMP_DIR: Path = Path("temp")

    # ELA Settings
    ELA_QUALITY: int = 90
    ELA_SCALE_FACTOR: float = 20.0

    # AI Detection Thresholds
    AI_DETECTION_THRESHOLD: float = 0.5
    FREQUENCY_ANOMALY_THRESHOLD: float = 0.4

    # Analysis Score Weights (tổng = 1.0)
    WEIGHT_EXIF: float = 0.30
    WEIGHT_ELA: float = 0.30
    WEIGHT_AI: float = 0.25
    WEIGHT_TIMESTAMP: float = 0.15
    
    # Telegram
    TELEGRAM_TOKEN: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
