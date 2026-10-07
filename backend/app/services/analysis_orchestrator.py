"""Analysis Orchestrator — Điều phối tất cả các module phân tích.

Chạy song song (hoặc tuần tự) các module phân tích,
tổng hợp kết quả và đưa ra verdict cuối cùng.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

from app.core.config import settings
from app.schemas.analysis import AnalysisResponse
from app.services import ai_detector, ela_engine, exif_analyzer, timestamp_verifier

logger = logging.getLogger(__name__)

# Ngưỡng verdict
AUTHENTIC_THRESHOLD = 70
SUSPICIOUS_THRESHOLD = 40

VERDICT_DESCRIPTIONS = {
    "AUTHENTIC": "Ảnh có vẻ chân thực, không phát hiện dấu hiệu chỉnh sửa đáng kể.",
    "SUSPICIOUS": "Ảnh có một số dấu hiệu đáng ngờ, cần kiểm tra thêm.",
    "MANIPULATED": "Ảnh có nhiều dấu hiệu bị chỉnh sửa hoặc tạo bởi AI.",
}


def _get_image_info(image_path: Path) -> dict:
    """Lấy thông tin cơ bản của ảnh."""
    try:
        with Image.open(image_path) as img:
            return {
                "width": img.width,
                "height": img.height,
                "format": img.format or "UNKNOWN",
                "mode": img.mode,
            }
    except Exception:
        logger.exception("Không đọc được thông tin ảnh")
        return {"width": 0, "height": 0, "format": "UNKNOWN", "mode": "UNKNOWN"}


def _determine_verdict(overall_score: int) -> tuple[str, str]:
    """Xác định verdict dựa trên overall score.

    Returns:
        Tuple (verdict_code, verdict_description).
    """
    if overall_score >= AUTHENTIC_THRESHOLD:
        verdict = "AUTHENTIC"
    elif overall_score >= SUSPICIOUS_THRESHOLD:
        verdict = "SUSPICIOUS"
    else:
        verdict = "MANIPULATED"

    return verdict, VERDICT_DESCRIPTIONS[verdict]


def _get_mime_type(image_path: Path) -> str:
    """Xác định MIME type từ extension."""
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".webp": "image/webp",
    }
    return mime_map.get(image_path.suffix.lower(), "application/octet-stream")


def run_full_analysis(image_path: str | Path, filename: str) -> AnalysisResponse:
    """Chạy phân tích toàn diện trên một ảnh.

    Thực hiện tuần tự 4 module phân tích, tổng hợp kết quả
    với trọng số đã cấu hình, và đưa ra verdict cuối cùng.

    Args:
        image_path: Đường dẫn đến file ảnh.
        filename: Tên file gốc (từ upload).

    Returns:
        AnalysisResponse với kết quả đầy đủ.
    """
    image_path = Path(image_path)

    # Thông tin cơ bản
    image_info = _get_image_info(image_path)
    file_size = image_path.stat().st_size

    # --- Chạy từng module phân tích ---
    logger.info("Bắt đầu phân tích EXIF cho %s", filename)
    exif_result = exif_analyzer.analyze(image_path)

    logger.info("Bắt đầu phân tích ELA cho %s", filename)
    ela_result = ela_engine.analyze(image_path)

    logger.info("Bắt đầu phân tích AI detection cho %s", filename)
    ai_result = ai_detector.analyze(image_path)

    logger.info("Bắt đầu kiểm tra timestamp cho %s", filename)
    timestamp_result = timestamp_verifier.analyze(image_path)

    # --- Tính overall score (weighted average) ---
    overall_score = int(
        exif_result.score * settings.WEIGHT_EXIF
        + ela_result.score * settings.WEIGHT_ELA
        + ai_result.score * settings.WEIGHT_AI
        + timestamp_result.score * settings.WEIGHT_TIMESTAMP
    )
    overall_score = max(0, min(100, overall_score))

    # --- Verdict ---
    verdict, verdict_description = _determine_verdict(overall_score)

    # --- Tổng hợp tất cả flags ---
    all_flags: list[str] = []
    all_flags.extend([f"[EXIF] {f}" for f in exif_result.flags])
    all_flags.extend([f"[ELA] {f}" for f in ela_result.flags])
    all_flags.extend([f"[AI] {f}" for f in ai_result.flags])
    all_flags.extend([f"[TIME] {f}" for f in timestamp_result.flags])

    logger.info(
        "Hoàn tất phân tích %s — Score: %d, Verdict: %s",
        filename, overall_score, verdict,
    )

    return AnalysisResponse(
        filename=filename,
        file_size_bytes=file_size,
        image_dimensions={"width": image_info["width"], "height": image_info["height"]},
        mime_type=_get_mime_type(image_path),
        overall_score=overall_score,
        verdict=verdict,
        verdict_description=verdict_description,
        exif_analysis=exif_result,
        ela_analysis=ela_result,
        ai_detection=ai_result,
        timestamp_verification=timestamp_result,
        all_flags=all_flags,
    )
