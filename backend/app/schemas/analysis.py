"""Pydantic schemas for analysis request/response data transfer objects."""
from __future__ import annotations

from pydantic import BaseModel, Field


class GpsCoordinates(BaseModel):
    """GPS location extracted from EXIF."""

    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None


class ExifResult(BaseModel):
    """Results from EXIF/Metadata analysis."""

    has_exif: bool = False
    capture_date: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    software: str | None = None
    gps: GpsCoordinates | None = None
    image_width: int | None = None
    image_height: int | None = None
    orientation: str | None = None
    color_space: str | None = None
    flash: str | None = None
    focal_length: str | None = None
    iso: str | None = None
    exposure_time: str | None = None
    f_number: str | None = None
    flags: list[str] = Field(default_factory=list)
    score: int = Field(default=50, ge=0, le=100)


class SuspiciousRegion(BaseModel):
    """A region in the image flagged as suspicious by ELA."""

    x: int
    y: int
    width: int
    height: int
    intensity: float = Field(ge=0.0, le=1.0)
    description: str = ""


class ElaResult(BaseModel):
    """Results from Error Level Analysis."""

    edited_regions_detected: bool = False
    heatmap_base64: str | None = None
    max_error_level: float = 0.0
    avg_error_level: float = 0.0
    suspicious_regions: list[SuspiciousRegion] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    score: int = Field(default=50, ge=0, le=100)


class AiDetectionResult(BaseModel):
    """Results from AI-generated image detection."""

    is_ai_generated: bool = False
    ai_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    frequency_anomaly_score: float = Field(default=0.0, ge=0.0, le=1.0)
    noise_consistency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    color_distribution_score: float = Field(default=0.0, ge=0.0, le=1.0)
    benford_law_score: float = Field(default=0.0, ge=0.0, le=1.0)
    detected_model: str | None = None
    flags: list[str] = Field(default_factory=list)
    score: int = Field(default=50, ge=0, le=100)


class TimestampResult(BaseModel):
    """Results from timestamp verification."""

    exif_timestamp: str | None = None
    metadata_modify_date: str | None = None
    is_consistent: bool = True
    time_zone_info: str | None = None
    flags: list[str] = Field(default_factory=list)
    score: int = Field(default=50, ge=0, le=100)


class AnalysisResponse(BaseModel):
    """Complete analysis response combining all modules."""

    filename: str
    file_size_bytes: int
    image_dimensions: dict[str, int]
    mime_type: str = ""

    # Tổng hợp
    overall_score: int = Field(
        default=50, ge=0, le=100, description="0=chắc chắn giả, 100=chắc chắn thật"
    )
    verdict: str = Field(
        default="UNKNOWN",
        description="AUTHENTIC | SUSPICIOUS | MANIPULATED",
    )
    verdict_description: str = ""

    # Kết quả từng module
    exif_analysis: ExifResult = Field(default_factory=ExifResult)
    ela_analysis: ElaResult = Field(default_factory=ElaResult)
    ai_detection: AiDetectionResult = Field(default_factory=AiDetectionResult)
    timestamp_verification: TimestampResult = Field(default_factory=TimestampResult)

    # Tổng hợp tất cả flags
    all_flags: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = ""
    modules_loaded: list[str] = Field(default_factory=list)
