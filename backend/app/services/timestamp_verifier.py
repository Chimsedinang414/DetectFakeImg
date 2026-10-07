"""Timestamp Verifier — Kiểm tra tính nhất quán của timestamp.

Module này so sánh và đánh giá:
1. Consistency giữa EXIF DateTimeOriginal và DateTimeDigitized
2. Phát hiện timestamp bất thường (tương lai, quá cũ)
3. Kiểm tra multiple compression indicators (dấu hiệu re-save)
4. So sánh file modification time vs EXIF time
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import exifread
from PIL import Image

from app.schemas.analysis import TimestampResult

logger = logging.getLogger(__name__)


def _parse_datetime(datetime_str: str) -> datetime | None:
    """Parse EXIF datetime string sang datetime object."""
    if not datetime_str:
        return None

    datetime_str = datetime_str.strip()
    formats = [
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(datetime_str, fmt)
        except ValueError:
            continue

    return None


def _check_jpeg_quality_tables(image_path: Path) -> list[str]:
    """Kiểm tra JPEG quantization tables để phát hiện double compression.

    Double compression = ảnh đã được save lại (có thể đã chỉnh sửa).
    """
    flags: list[str] = []

    try:
        with Image.open(image_path) as img:
            if img.format != "JPEG":
                return flags

            # Pillow không expose trực tiếp quantization tables
            # nhưng ta có thể kiểm tra qua info dict
            quantization = img.quantization
            if quantization:
                # Nếu có nhiều hơn 2 bảng (thường JPEG có 2: luminance + chrominance)
                if len(quantization) > 2:
                    flags.append("⚠️ Phát hiện nhiều quantization tables bất thường")

                # Kiểm tra quality estimate
                # Bảng luminance thường ở index 0
                if 0 in quantization:
                    lum_table = quantization[0]
                    # Quality cao (~95+): hầu hết giá trị gần 1
                    # Quality thấp (~50-): nhiều giá trị > 50
                    avg_quant = sum(lum_table) / len(lum_table)
                    if avg_quant < 3:
                        flags.append("ℹ️ JPEG quality rất cao (95+)")
                    elif avg_quant < 10:
                        flags.append("ℹ️ JPEG quality cao (80-95)")
                    elif avg_quant < 30:
                        flags.append("ℹ️ JPEG quality trung bình (50-80)")
                    else:
                        flags.append("⚠️ JPEG quality thấp (<50) — có thể đã re-compress nhiều lần")

    except Exception:
        logger.debug("Không đọc được quantization tables")

    return flags


def analyze(image_path: str | Path) -> TimestampResult:
    """Kiểm tra tính nhất quán của timestamps trong ảnh.

    Args:
        image_path: Đường dẫn đến file ảnh.

    Returns:
        TimestampResult chứa thông tin timestamp và đánh giá.
    """
    result = TimestampResult()
    flags: list[str] = []
    score = 100
    is_consistent = True

    image_path = Path(image_path)

    # --- Đọc EXIF timestamps ---
    try:
        with open(image_path, "rb") as f:
            tags = exifread.process_file(f, details=False)
    except Exception:
        logger.exception("Lỗi đọc EXIF")
        tags = {}

    datetime_original = tags.get("EXIF DateTimeOriginal")
    datetime_digitized = tags.get("EXIF DateTimeDigitized")
    datetime_modified = tags.get("Image DateTime")
    offset_time = tags.get("EXIF OffsetTime")

    # --- Parse timestamps ---
    dt_original = _parse_datetime(str(datetime_original)) if datetime_original else None
    dt_digitized = _parse_datetime(str(datetime_digitized)) if datetime_digitized else None
    dt_modified = _parse_datetime(str(datetime_modified)) if datetime_modified else None

    if dt_original:
        result.exif_timestamp = dt_original.isoformat()
        flags.append(f"📅 DateTimeOriginal: {dt_original.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        flags.append("⚠️ Không có DateTimeOriginal trong EXIF")
        score -= 20
        is_consistent = False

    if offset_time:
        result.time_zone_info = str(offset_time)
        flags.append(f"🕐 Timezone: {offset_time}")

    # --- Kiểm tra consistency giữa Original và Digitized ---
    if dt_original and dt_digitized:
        diff_seconds = abs((dt_original - dt_digitized).total_seconds())
        if diff_seconds > 2:
            flags.append(
                f"🔴 DateTimeOriginal và DateTimeDigitized chênh nhau {diff_seconds:.0f} giây"
            )
            score -= 15
            is_consistent = False
        else:
            flags.append("✅ DateTimeOriginal và DateTimeDigitized nhất quán")

    # --- Kiểm tra Modified vs Original ---
    if dt_original and dt_modified:
        diff_seconds = abs((dt_original - dt_modified).total_seconds())
        result.metadata_modify_date = dt_modified.isoformat()

        if diff_seconds > 60:
            flags.append(
                f"🔴 Ảnh đã bị chỉnh sửa sau khi chụp "
                f"(chênh {diff_seconds / 3600:.1f} giờ)"
            )
            score -= 25
            is_consistent = False
        elif diff_seconds > 2:
            flags.append(f"⚠️ DateTime có chênh nhẹ ({diff_seconds:.0f}s) — có thể do processing")
            score -= 5

    # --- Kiểm tra timestamp bất thường ---
    now = datetime.now()

    if dt_original:
        # Ảnh từ tương lai?
        if dt_original > now:
            flags.append("🔴 Timestamp là TƯƠNG LAI — chắc chắn bất thường!")
            score -= 40
            is_consistent = False

        # Ảnh quá cũ? (trước 2000)
        if dt_original.year < 2000:
            flags.append(f"⚠️ Timestamp rất cũ ({dt_original.year}) — có thể clock sai")
            score -= 10

    # --- Kiểm tra file modification time ---
    try:
        file_mtime = datetime.fromtimestamp(os.path.getmtime(image_path))
        if dt_original:
            file_vs_exif = abs((file_mtime - dt_original).total_seconds())
            # Nếu file mtime quá khác EXIF → file đã bị copy/modify
            if file_vs_exif > 86400:  # > 1 ngày
                flags.append(
                    f"ℹ️ File modification time ({file_mtime.strftime('%Y-%m-%d')}) "
                    f"khác EXIF ({dt_original.strftime('%Y-%m-%d')}) — file đã được copy/di chuyển"
                )
    except OSError:
        pass

    # --- JPEG Quality Analysis ---
    jpeg_flags = _check_jpeg_quality_tables(image_path)
    flags.extend(jpeg_flags)

    result.is_consistent = is_consistent
    result.flags = flags
    result.score = max(0, min(100, score))

    return result
