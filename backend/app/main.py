"""FastAPI Application Entry Point."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings

# Logging setup
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "API phân tích và phát hiện ảnh giả mạo cho hệ thống chấm công xây dựng. "
        "Hỗ trợ phân tích EXIF metadata, Error Level Analysis (ELA), "
        "AI detection, và timestamp verification."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware — cho phép frontend gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount router
app.include_router(router, prefix="/api")


@app.on_event("startup")
async def startup_event() -> None:
    """Khởi tạo resources khi server start."""
    logger.info("🚀 %s v%s đang khởi động...", settings.APP_NAME, settings.APP_VERSION)

    # Tạo thư mục upload nếu chưa có
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("✅ Server sẵn sàng!")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup resources khi server shutdown."""
    logger.info("🛑 Server đang tắt...")
