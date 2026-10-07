"""EXIF/Metadata Analyzer — Trích xuất và đánh giá metadata ảnh.

Module này đọc EXIF data từ ảnh để xác định:
- Thời gian chụp gốc
- Thiết bị chụp (camera make/model)
- Phần mềm chỉnh sửa (nếu có)
- Tọa độ GPS
- Các dấu hiệu bất thường trong metadata
"""
from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path

import exifread
from PIL import Image

from app.schemas.analysis import ExifResult, GpsCoordinates

logger = logging.getLogger(__name__)

# Phần mềm chỉnh sửa phổ biến — nếu phát hiện → ảnh đã qua xử lý
EDITING_SOFTWARE_KEYWORDS: list[str] = [
    "photoshop",
    "lightroom",
    "gimp",
    "snapseed",
    "vsco",
    "afterlight",
    "picsart",
    "canva",
    "pixlr",
    "fotor",
    "polarr",
    "darktable",
    "capture one",
    "affinity",
    "luminar",
    "photoscape",
    "paint.net",
    "acdsee",
    "corel",
    "facetune",
    "meitu",
    "beauty plus",
    "remini",
    "faceapp",
    "stable diffusion",
    "midjourney",
    "dall-e",
    "comfyui",
    "automatic1111",
]


def _convert_gps_to_decimal(gps_values: list, gps_ref: str) -> float | None:
    """Chuyển đổi tọa độ GPS từ format degrees/minutes/seconds sang decimal."""
    try:
        degrees = float(gps_values[0])
        minutes = float(gps_values[1])
        seconds = float(gps_values[2])

        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)

        if gps_ref in ("S", "W"):
            decimal = -decimal

        return round(decimal, 6)
    except (ValueError, IndexError, TypeError):
        logger.warning("Không thể chuyển đổi GPS coordinates")
        return None


def _extract_gps(tags: dict) -> GpsCoordinates | None:
    """Trích xuất GPS coordinates từ EXIF tags."""
    lat_tag = tags.get("GPS GPSLatitude")
    lat_ref_tag = tags.get("GPS GPSLatitudeRef")
    lon_tag = tags.get("GPS GPSLongitude")
    lon_ref_tag = tags.get("GPS GPSLongitudeRef")
    alt_tag = tags.get("GPS GPSAltitude")

    if not (lat_tag and lon_tag):
        return None

    lat_ref = str(lat_ref_tag) if lat_ref_tag else "N"
    lon_ref = str(lon_ref_tag) if lon_ref_tag else "E"

    latitude = _convert_gps_to_decimal(lat_tag.values, lat_ref)
    longitude = _convert_gps_to_decimal(lon_tag.values, lon_ref)

    altitude = None
    if alt_tag:
        try:
            altitude = float(alt_tag.values[0])
        except (ValueError, IndexError):
            pass

    if latitude is not None and longitude is not None:
        return GpsCoordinates(latitude=latitude, longitude=longitude, altitude=altitude)

    return None


def _detect_editing_software(software_str: str) -> str | None:
    """Kiểm tra xem software tag có chứa tên phần mềm chỉnh sửa không."""
    if not software_str:
        return None

    software_lower = software_str.lower()
    for keyword in EDITING_SOFTWARE_KEYWORDS:
        if keyword in software_lower:
            return keyword

    return None


def _parse_exif_datetime(datetime_str: str) -> str | None:
    """Parse EXIF datetime string sang ISO format."""
    if not datetime_str:
        return None

    datetime_str = datetime_str.strip()
    formats = [
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(datetime_str, fmt)
            return dt.isoformat()
        except ValueError:
            continue

    return datetime_str


def analyze(image_path: str | Path) -> ExifResult:
    """Phân tích EXIF metadata của ảnh.

    Args:
        image_path: Đường dẫn đến file ảnh.

    Returns:
        ExifResult chứa metadata và điểm đánh giá.
    """
    result = ExifResult()
    flags: list[str] = []
    score = 100  # Bắt đầu với 100, trừ điểm khi phát hiện bất thường

    image_path = Path(image_path)

    # --- Đọc EXIF bằng exifread (chi tiết hơn Pillow) ---
    try:
        with open(image_path, "rb") as f:
            tags = exifread.process_file(f, details=True)
    except Exception:
        logger.exception("Lỗi đọc EXIF từ file %s", image_path)
        tags = {}

    if not tags:
        result.has_exif = False
        flags.append("⚠️ KHÔNG CÓ EXIF DATA — Ảnh có thể đã bị strip metadata")
        score -= 40
        result.flags = flags
        result.score = max(0, score)
        return result

    result.has_exif = True
    flags.append("✅ Có EXIF metadata")

    # --- Camera Info ---
    make_tag = tags.get("Image Make")
    model_tag = tags.get("Image Model")
    if make_tag:
        result.camera_make = str(make_tag).strip()
    if model_tag:
        result.camera_model = str(model_tag).strip()

    if result.camera_make or result.camera_model:
        flags.append(f"📷 Thiết bị: {result.camera_make or ''} {result.camera_model or ''}".strip())
    else:
        flags.append("⚠️ Không có thông tin thiết bị chụp")
        score -= 10

    # --- Software ---
    software_tag = tags.get("Image Software")
    if software_tag:
        result.software = str(software_tag).strip()
        detected = _detect_editing_software(result.software)
        if detected:
            flags.append(f"🔴 Phát hiện phần mềm chỉnh sửa: {detected.upper()}")
            score -= 30
        else:
            flags.append(f"ℹ️ Software: {result.software}")

    # --- Timestamps ---
    datetime_original = tags.get("EXIF DateTimeOriginal")
    datetime_digitized = tags.get("EXIF DateTimeDigitized")
    datetime_modified = tags.get("Image DateTime")

    if datetime_original:
        result.capture_date = _parse_exif_datetime(str(datetime_original))
        flags.append(f"📅 Thời gian chụp gốc: {result.capture_date}")
    else:
        flags.append("⚠️ Không có DateTimeOriginal — không xác định được thời gian chụp gốc")
        score -= 15

    # Kiểm tra sự không nhất quán giữa các timestamps
    if datetime_original and datetime_modified:
        orig_str = str(datetime_original).strip()
        mod_str = str(datetime_modified).strip()
        if orig_str != mod_str:
            flags.append(
                f"🔴 Thời gian chỉnh sửa ({mod_str}) KHÁC thời gian chụp gốc ({orig_str})"
            )
            score -= 20

    # --- GPS ---
    gps = _extract_gps(tags)
    if gps:
        result.gps = gps
        flags.append(f"📍 GPS: {gps.latitude}, {gps.longitude}")
    else:
        flags.append("ℹ️ Không có thông tin GPS")

    # --- Thông số kỹ thuật ---
    orientation_tag = tags.get("Image Orientation")
    if orientation_tag:
        result.orientation = str(orientation_tag)

    flash_tag = tags.get("EXIF Flash")
    if flash_tag:
        result.flash = str(flash_tag)

    focal_tag = tags.get("EXIF FocalLength")
    if focal_tag:
        result.focal_length = str(focal_tag)

    iso_tag = tags.get("EXIF ISOSpeedRatings")
    if iso_tag:
        result.iso = str(iso_tag)

    exposure_tag = tags.get("EXIF ExposureTime")
    if exposure_tag:
        result.exposure_time = str(exposure_tag)

    fnumber_tag = tags.get("EXIF FNumber")
    if fnumber_tag:
        result.f_number = str(fnumber_tag)

    # --- Image dimensions từ Pillow (chính xác hơn EXIF) ---
    try:
        with Image.open(image_path) as img:
            result.image_width = img.width
            result.image_height = img.height
    except Exception:
        logger.warning("Không đọc được dimensions từ Pillow")

    # --- Kiểm tra thumbnail nhúng ---
    thumbnail_tag = tags.get("JPEGThumbnail")
    if thumbnail_tag:
        flags.append("ℹ️ Có thumbnail nhúng trong EXIF")
        # Kiểm tra thumbnail có khớp ảnh gốc không
        try:
            thumb_img = Image.open(BytesIO(thumbnail_tag))
            with Image.open(image_path) as orig_img:
                orig_aspect = orig_img.width / orig_img.height
                thumb_aspect = thumb_img.width / thumb_img.height
                if abs(orig_aspect - thumb_aspect) > 0.1:
                    flags.append("🔴 Thumbnail có tỷ lệ khác ảnh gốc — có thể bị chỉnh sửa")
                    score -= 15
        except Exception:
            pass

    result.flags = flags
    result.score = max(0, min(100, score))

    return result
