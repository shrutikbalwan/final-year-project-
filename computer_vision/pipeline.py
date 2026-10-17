from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Iterator
from urllib.parse import urlsplit
from uuid import uuid4

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from contracts.v1 import SafetyEvent
from contracts.v1.models import EventSeverity, EventType

from .detector import Detection, Detector, UltralyticsYoloDetector
from .errors import InvalidImageError, UnsupportedClassError, VideoSourceError


class RestrictedZone(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    zone_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    polygon: list[tuple[float, float]] = Field(min_length=3, max_length=128)

    @field_validator("polygon")
    @classmethod
    def normalized_polygon(cls, polygon):
        if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in polygon):
            raise ValueError("restricted-zone coordinates must be normalized from 0 to 1")
        return polygon


@dataclass(frozen=True)
class ZoneEntry:
    zone_id: str
    tracker_id: int
    event: SafetyEvent


@dataclass(frozen=True)
class FrameResult:
    frame_index: int
    inference_ms: float
    detections: tuple[Detection, ...]
    zone_entries: tuple[ZoneEntry, ...]


class VisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: str = "yolov8n.pt"
    model_class_names: list[str] | None = None
    confidence: float = Field(default=0.25, gt=0, le=1)
    device: str = "cpu"
    camera_id: str = Field(min_length=1, max_length=128)
    workplace_id: str = Field(min_length=1, max_length=128)
    person_class_names: list[str] = Field(default_factory=lambda: ["person"])
    requested_classes: list[str] | None = None
    restricted_zones: list[RestrictedZone] = Field(default_factory=list)


class SafetyVisionPipeline:
    """Frame-at-a-time inference; frames are never stored by this pipeline."""

    def __init__(self, config: VisionConfig, detector: Detector | None = None) -> None:
        self.config = config
        self.detector = detector or UltralyticsYoloDetector(
            config.weights, config.confidence, config.device, config.model_class_names
        )
        normalized_names = {name.casefold(): class_id for class_id, name in self.detector.class_names.items()}
        self.requested_class_ids: set[int] | None = None
        if config.requested_classes is not None:
            missing = [name for name in config.requested_classes if name.casefold() not in normalized_names]
            if missing:
                raise UnsupportedClassError(
                    f"Selected model does not support requested classes: {', '.join(missing)}"
                )
            self.requested_class_ids = {
                normalized_names[name.casefold()] for name in config.requested_classes
            }
        self.person_class_ids = {
            normalized_names[name.casefold()]
            for name in config.person_class_names
            if name.casefold() in normalized_names
        }
        if config.restricted_zones and not self.person_class_ids:
            raise UnsupportedClassError(
                "Restricted-zone alerts require a person class supported by the selected model"
            )
        if (
            config.restricted_zones
            and self.requested_class_ids is not None
            and not self.person_class_ids.intersection(self.requested_class_ids)
        ):
            raise UnsupportedClassError(
                "requested_classes must include a supported person class when restricted zones are configured"
            )
        self._active_zone_tracks: set[tuple[str, int]] = set()

    @classmethod
    def from_config(cls, config: VisionConfig) -> "SafetyVisionPipeline":
        return cls(config)

    def process_frame(self, frame: np.ndarray, frame_index: int = 0) -> FrameResult:
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            raise InvalidImageError("Frame is empty or invalid")
        started = perf_counter()
        detections = self.detector.detect(frame, track=bool(self.config.restricted_zones))
        inference_ms = (perf_counter() - started) * 1000
        if self.requested_class_ids is not None:
            detections = [d for d in detections if d.class_id in self.requested_class_ids]
        entered, active = [], set()
        height, width = frame.shape[:2]
        for detection in detections:
            if detection.class_id not in self.person_class_ids or detection.tracker_id is None:
                continue
            x1, y1, x2, y2 = detection.bbox_xyxy
            center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            for zone in self.config.restricted_zones:
                polygon = np.array(
                    [(int(x * width), int(y * height)) for x, y in zone.polygon],
                    dtype=np.int32,
                )
                if cv2.pointPolygonTest(polygon, center, False) >= 0:
                    key = (zone.zone_id, detection.tracker_id)
                    active.add(key)
                    if key not in self._active_zone_tracks:
                        entered.append(self._zone_event(zone.zone_id, detection.tracker_id))
        self._active_zone_tracks = active
        return FrameResult(frame_index, inference_ms, tuple(detections), tuple(entered))

    def process_image(self, image_path: str | Path) -> FrameResult:
        frame = cv2.imread(str(image_path))
        if frame is None:
            raise InvalidImageError(f"Could not load image: {image_path}")
        return self.process_frame(frame, 0)

    def iter_video(
        self,
        source: str | Path | int,
        *,
        max_frames: int | None = None,
    ) -> Iterator[FrameResult]:
        try:
            capture = cv2.VideoCapture(str(source) if isinstance(source, Path) else source)
        except Exception as exc:
            raise VideoSourceError("Could not initialize video capture source") from exc
        if not capture.isOpened():
            capture.release()
            label = "RTSP source" if isinstance(source, str) and source.casefold().startswith(("rtsp://", "rtsps://")) else str(source)
            raise VideoSourceError(f"Could not open video source: {label}")
        frame_index = 0
        try:
            while max_frames is None or frame_index < max_frames:
                try:
                    ok, frame = capture.read()
                except Exception as exc:
                    raise VideoSourceError("Video source failed while reading a frame") from exc
                if not ok:
                    if frame_index == 0:
                        raise VideoSourceError("Video source opened but produced no frames")
                    break
                yield self.process_frame(frame, frame_index)
                frame_index += 1
        finally:
            capture.release()

    def iter_recorded_video(
        self, video_path: str | Path, *, max_frames: int | None = None
    ) -> Iterator[FrameResult]:
        return self.iter_video(video_path, max_frames=max_frames)

    def iter_webcam(
        self, camera_index: int = 0, *, max_frames: int | None = None
    ) -> Iterator[FrameResult]:
        return self.iter_video(camera_index, max_frames=max_frames)

    def iter_rtsp(
        self, rtsp_url: str, *, max_frames: int | None = None
    ) -> Iterator[FrameResult]:
        try:
            parsed = urlsplit(rtsp_url)
        except ValueError as exc:
            raise VideoSourceError("RTSP source must be a valid rtsp:// or rtsps:// URL") from exc
        if parsed.scheme.casefold() not in {"rtsp", "rtsps"} or not parsed.hostname:
            raise VideoSourceError("RTSP source must be a valid rtsp:// or rtsps:// URL")
        # Never echo a URL that may contain credentials into an exception or log.
        return self.iter_video(rtsp_url, max_frames=max_frames)

    def _zone_event(self, zone_id: str, tracker_id: int) -> ZoneEntry:
        now = datetime.now(timezone.utc)
        event = SafetyEvent(
            schema_version="1.0.0",
            event_id=f"vision-{uuid4().hex}",
            device_id=self.config.camera_id,
            workplace_id=self.config.workplace_id,
            event_type=EventType.HAZARD_DETECTED,
            severity=EventSeverity.UNKNOWN,
            occurred_at=now,
            reported_at=now,
            description=(
                f"Tracked person {tracker_id} entered configured restricted zone '{zone_id}'. "
                "Computer-vision event requires human review."
            ),
        )
        return ZoneEntry(zone_id, tracker_id, event)
