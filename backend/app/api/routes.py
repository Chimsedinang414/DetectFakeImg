"""API Routes — Endpoints cho phân tích ảnh."""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.core.config import settings
from app.schemas.analysis import AnalysisResponse, HealthResponse
from app.services import analysis_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter()


def _validate_file(file: UploadFile) -> None:
    """Kiểm tra file upload hợp lệ."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tên file không hợp lệ.",
        )

    extension = Path(file.filename).suffix.lower()
    if extension not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Định dạng '{extension}' không được hỗ trợ. "
                   f"Chấp nhận: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )


async def _save_upload(file: UploadFile) -> Path:
    """Lưu file upload vào thư mục tạm."""
    upload_dir = settings.UPLOAD_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Tạo tên file unique để tránh conflict
    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = upload_dir / unique_name

    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()

            # Kiểm tra kích thước
            size_mb = len(content) / (1024 * 1024)
            if size_mb > settings.MAX_UPLOAD_SIZE_MB:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File quá lớn ({size_mb:.1f}MB). "
                           f"Tối đa: {settings.MAX_UPLOAD_SIZE_MB}MB",
                )

            buffer.write(content)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Lỗi lưu file upload")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi lưu file upload.",
        ) from exc

    return file_path


def _cleanup_file(file_path: Path) -> None:
    """Xóa file tạm sau khi phân tích xong."""
    try:
        if file_path.exists():
            file_path.unlink()
    except OSError:
        logger.warning("Không xóa được file tạm: %s", file_path)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Kiểm tra trạng thái server."""
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        modules_loaded=["exif_analyzer", "ela_engine", "ai_detector", "timestamp_verifier"],
    )


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_image(file: UploadFile) -> AnalysisResponse:
    """Phân tích toàn diện một ảnh.

    Upload ảnh và nhận kết quả phân tích từ tất cả 4 module:
    - EXIF/Metadata Analysis
    - Error Level Analysis (ELA)
    - AI Detection
    - Timestamp Verification
    """
    _validate_file(file)

    file_path = await _save_upload(file)

    try:
        result = analysis_orchestrator.run_full_analysis(
            image_path=file_path,
            filename=file.filename or "unknown",
        )
        return result
    except Exception as exc:
        logger.exception("Lỗi phân tích ảnh %s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi phân tích ảnh: {exc!s}",
        ) from exc
    finally:
        _cleanup_file(file_path)


@router.post("/analyze/batch", response_model=list[AnalysisResponse])
async def analyze_batch(files: list[UploadFile]) -> list[AnalysisResponse]:
    """Phân tích hàng loạt nhiều ảnh cùng lúc.

    Giới hạn 20 ảnh mỗi lần để tránh quá tải server.
    """
    max_batch = 20
    if len(files) > max_batch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tối đa {max_batch} ảnh mỗi lần. Nhận được {len(files)} ảnh.",
        )

    results: list[AnalysisResponse] = []
    saved_paths: list[Path] = []

    try:
        for file in files:
            _validate_file(file)
            file_path = await _save_upload(file)
            saved_paths.append(file_path)

            result = analysis_orchestrator.run_full_analysis(
                image_path=file_path,
                filename=file.filename or "unknown",
            )
            results.append(result)
    finally:
        for path in saved_paths:
            _cleanup_file(path)

    return results
