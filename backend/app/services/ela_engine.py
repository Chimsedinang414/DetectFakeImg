"""ELA (Error Level Analysis) Engine — Phát hiện vùng bị chỉnh sửa trong ảnh.

Nguyên lý hoạt động:
1. Ảnh JPEG gốc đã được nén ở một quality level nhất định
2. Khi re-compress ảnh ở quality level đã biết, các vùng CHƯA chỉnh sửa
   sẽ có error level đồng đều (vì đã được nén trước đó)
3. Các vùng BỊ CHỈNH SỬA sẽ có error level khác biệt (cao hơn hoặc thấp hơn)
   vì chúng được nén ở quality level khác hoặc được chèn từ nguồn khác
4. Bằng cách amplify sự khác biệt, ta có thể visualize vùng bị chỉnh sửa
"""
from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance

from app.core.config import settings
from app.schemas.analysis import ElaResult, SuspiciousRegion

logger = logging.getLogger(__name__)

# Ngưỡng để xác định vùng "đáng ngờ" trong ELA
SUSPICIOUS_THRESHOLD_RATIO = 0.6  # 60% của max error level
MIN_CONTOUR_AREA = 500  # Bỏ qua vùng quá nhỏ (pixel²)


def _compute_ela_difference(image_path: Path, quality: int) -> tuple[np.ndarray, Image.Image]:
    """Tính toán ELA difference map.

    Args:
        image_path: Đường dẫn ảnh gốc.
        quality: JPEG quality level cho re-compression.

    Returns:
        Tuple (numpy array dạng grayscale, PIL Image dạng RGB) của difference map.
    """
    original = Image.open(image_path).convert("RGB")

    # Re-compress ảnh ở quality đã biết
    buffer = BytesIO()
    original.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    resaved = Image.open(buffer).convert("RGB")

    # Tính difference
    diff = ImageChops.difference(original, resaved)

    return np.array(diff), diff


def _amplify_difference(diff_array: np.ndarray, scale_factor: float) -> np.ndarray:
    """Amplify difference map để dễ nhìn hơn.

    Args:
        diff_array: Numpy array từ ELA difference.
        scale_factor: Hệ số amplify.

    Returns:
        Amplified difference map (0-255).
    """
    amplified = diff_array.astype(np.float64) * scale_factor
    amplified = np.clip(amplified, 0, 255).astype(np.uint8)
    return amplified


def _create_heatmap(diff_gray: np.ndarray) -> np.ndarray:
    """Tạo heatmap màu từ grayscale difference map.

    Args:
        diff_gray: Grayscale difference (0-255).

    Returns:
        BGR heatmap image.
    """
    # Normalize về 0-255
    if diff_gray.max() > 0:
        normalized = ((diff_gray / diff_gray.max()) * 255).astype(np.uint8)
    else:
        normalized = diff_gray.astype(np.uint8)

    # Apply colormap — COLORMAP_JET cho kết quả trực quan tốt
    heatmap = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)

    return heatmap


def _find_suspicious_regions(
    diff_gray: np.ndarray,
    threshold_ratio: float = SUSPICIOUS_THRESHOLD_RATIO,
) -> list[SuspiciousRegion]:
    """Tìm các vùng có error level cao bất thường.

    Args:
        diff_gray: Grayscale difference map.
        threshold_ratio: Ngưỡng so với max error level.

    Returns:
        Danh sách các vùng đáng ngờ.
    """
    max_val = diff_gray.max()
    if max_val == 0:
        return []

    threshold = int(max_val * threshold_ratio)
    _, binary = cv2.threshold(diff_gray, threshold, 255, cv2.THRESH_BINARY)

    # Morphological operations để giảm noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions: list[SuspiciousRegion] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < MIN_CONTOUR_AREA:
            continue

        x, y, w, h = cv2.boundingRect(contour)

        # Tính intensity trung bình trong vùng
        region_pixels = diff_gray[y : y + h, x : x + w]
        avg_intensity = float(region_pixels.mean()) / 255.0

        regions.append(
            SuspiciousRegion(
                x=int(x),
                y=int(y),
                width=int(w),
                height=int(h),
                intensity=round(avg_intensity, 3),
                description=f"Vùng ({x},{y}) kích thước {w}x{h} — intensity: {avg_intensity:.1%}",
            )
        )

    # Sắp xếp theo intensity giảm dần
    regions.sort(key=lambda r: r.intensity, reverse=True)

    return regions[:20]  # Giới hạn 20 vùng đáng ngờ nhất


def _image_to_base64(image: np.ndarray) -> str:
    """Chuyển numpy array (BGR) sang base64 PNG string."""
    _, buffer = cv2.imencode(".png", image)
    return base64.b64encode(buffer.tobytes()).decode("utf-8")


def analyze(image_path: str | Path) -> ElaResult:
    """Thực hiện Error Level Analysis trên ảnh.

    Args:
        image_path: Đường dẫn đến file ảnh.

    Returns:
        ElaResult chứa heatmap, vùng đáng ngờ, và điểm đánh giá.
    """
    result = ElaResult()
    flags: list[str] = []
    score = 100

    image_path = Path(image_path)

    try:
        # 1. Compute ELA difference
        diff_array, _ = _compute_ela_difference(image_path, settings.ELA_QUALITY)

        # 2. Convert sang grayscale cho analysis
        diff_gray = cv2.cvtColor(diff_array, cv2.COLOR_RGB2GRAY)

        # 3. Amplify difference
        amplified = _amplify_difference(diff_array, settings.ELA_SCALE_FACTOR)
        amplified_gray = cv2.cvtColor(amplified, cv2.COLOR_RGB2GRAY)

        # 4. Tính các metrics
        max_error = float(diff_gray.max())
        avg_error = float(diff_gray.mean())
        std_error = float(diff_gray.std())

        result.max_error_level = round(max_error, 2)
        result.avg_error_level = round(avg_error, 2)

        # 5. Tạo heatmap
        heatmap = _create_heatmap(amplified_gray)

        # Overlay heatmap lên ảnh gốc
        original_cv = cv2.imread(str(image_path))
        if original_cv is not None:
            original_resized = cv2.resize(
                original_cv, (heatmap.shape[1], heatmap.shape[0])
            )
            overlay = cv2.addWeighted(original_resized, 0.5, heatmap, 0.5, 0)
            result.heatmap_base64 = _image_to_base64(overlay)
        else:
            result.heatmap_base64 = _image_to_base64(heatmap)

        # 6. Tìm vùng đáng ngờ
        regions = _find_suspicious_regions(amplified_gray)
        result.suspicious_regions = regions

        # 7. Đánh giá
        if len(regions) == 0:
            flags.append("✅ Không phát hiện vùng chỉnh sửa rõ ràng")
        else:
            result.edited_regions_detected = True
            flags.append(f"🔴 Phát hiện {len(regions)} vùng có dấu hiệu chỉnh sửa")
            score -= min(40, len(regions) * 10)

        # Kiểm tra std deviation — ảnh chỉnh sửa thường có std cao
        if std_error > 15:
            flags.append(f"⚠️ Độ lệch chuẩn error level cao ({std_error:.1f}) — có thể bị chỉnh sửa")
            score -= 15
        elif std_error > 8:
            flags.append(f"ℹ️ Độ lệch chuẩn error level trung bình ({std_error:.1f})")
            score -= 5

        # Kiểm tra max error — quá cao = chỉnh sửa nặng
        if max_error > 100:
            flags.append(f"🔴 Error level tối đa rất cao ({max_error:.0f}/255)")
            score -= 20
        elif max_error > 50:
            flags.append(f"⚠️ Error level tối đa cao ({max_error:.0f}/255)")
            score -= 10

    except Exception:
        logger.exception("Lỗi ELA analysis cho file %s", image_path)
        flags.append("❌ Lỗi khi phân tích ELA")
        score = 50

    result.flags = flags
    result.score = max(0, min(100, score))

    return result
