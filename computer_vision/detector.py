from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from .errors import InferenceError, ModelLoadError


@dataclass(frozen=True)
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    tracker_id: int | None = None


class Detector(Protocol):
    @property
    def class_names(self) -> dict[int, str]: ...

    def detect(self, frame: np.ndarray, *, track: bool = False) -> list[Detection]: ...


class UltralyticsYoloDetector:
    """Adapter for Ultralytics YOLO weights; inference defaults to CPU."""

    def __init__(
        self,
        weights: str | Path,
        confidence: float = 0.25,
        device: str = "cpu",
        class_names: list[str] | None = None,
    ) -> None:
        self.confidence = confidence
        self.device = device
        self._onnx = str(weights).casefold().endswith(".onnx")
        if self._onnx:
            if not class_names:
                raise ModelLoadError("ONNX YOLO weights require class_names from their model metadata")
            try:
                import cv2

                self.net = cv2.dnn.readNetFromONNX(str(weights))
                self._class_names = {index: name for index, name in enumerate(class_names)}
            except Exception as exc:
                raise ModelLoadError(
                    f"Could not load ONNX YOLO weights '{weights}'. Verify the local ONNX file."
                ) from exc
            return
        try:
            from ultralytics import YOLO

            self.model = YOLO(str(weights))
        except Exception as exc:
            raise ModelLoadError(
                f"Could not load YOLO weights '{weights}'. Install requirements-cv.txt and verify the local weights path."
            ) from exc
        names = self.model.names
        self._class_names = (
            {int(key): str(value) for key, value in names.items()}
            if isinstance(names, dict)
            else {index: str(value) for index, value in enumerate(names)}
        )

    @property
    def class_names(self) -> dict[int, str]:
        return dict(self._class_names)

    def detect(self, frame: np.ndarray, *, track: bool = False) -> list[Detection]:
        if self._onnx:
            if track:
                raise InferenceError("This ONNX detector does not provide person tracking")
            return self._detect_onnx(frame)
        try:
            results = (
                self.model.track(
                    frame,
                    persist=True,
                    conf=self.confidence,
                    device=self.device,
                    verbose=False,
                )
                if track
                else self.model.predict(
                    frame,
                    conf=self.confidence,
                    device=self.device,
                    verbose=False,
                )
            )
            boxes = results[0].boxes
            if boxes is None:
                return []
            coords = boxes.xyxy.cpu().tolist()
            classes = boxes.cls.cpu().tolist()
            scores = boxes.conf.cpu().tolist()
            ids = boxes.id.cpu().tolist() if track and boxes.id is not None else [None] * len(coords)
            return [
                Detection(
                    class_id=int(class_id),
                    class_name=self._class_names[int(class_id)],
                    confidence=float(score),
                    bbox_xyxy=tuple(float(value) for value in box),
                    tracker_id=int(ids[index]) if ids[index] is not None else None,
                )
                for index, (box, class_id, score) in enumerate(zip(coords, classes, scores))
            ]
        except Exception as exc:
            raise InferenceError("YOLO inference failed for the current frame") from exc

    def _detect_onnx(self, frame: np.ndarray) -> list[Detection]:
        import cv2

        try:
            height, width = frame.shape[:2]
            target = 640
            scale = min(target / width, target / height)
            resized_width, resized_height = round(width * scale), round(height * scale)
            resized = cv2.resize(frame, (resized_width, resized_height))
            left = (target - resized_width) // 2
            top = (target - resized_height) // 2
            canvas = np.full((target, target, 3), 114, dtype=np.uint8)
            canvas[top : top + resized_height, left : left + resized_width] = resized
            blob = cv2.dnn.blobFromImage(
                canvas, scalefactor=1 / 255.0, size=(target, target), swapRB=True, crop=False
            )
            self.net.setInput(blob)
            output = np.asarray(self.net.forward())
            if output.ndim == 3:
                output = output[0]
            channels = 4 + len(self._class_names)
            if output.ndim != 2:
                raise ValueError("unexpected ONNX output rank")
            if output.shape[0] == channels:
                rows = output.T
            elif output.shape[1] == channels:
                rows = output
            else:
                raise ValueError("ONNX output does not match configured class count")

            candidates: dict[int, list[tuple[list[int], float, tuple[float, float, float, float]]]] = {}
            for row in rows:
                scores = row[4:]
                class_id = int(np.argmax(scores))
                confidence = float(scores[class_id])
                if confidence < self.confidence:
                    continue
                center_x, center_y, box_width, box_height = (float(value) for value in row[:4])
                x1 = (center_x - box_width / 2 - left) / scale
                y1 = (center_y - box_height / 2 - top) / scale
                x2 = (center_x + box_width / 2 - left) / scale
                y2 = (center_y + box_height / 2 - top) / scale
                box = (
                    max(0.0, min(float(width), x1)),
                    max(0.0, min(float(height), y1)),
                    max(0.0, min(float(width), x2)),
                    max(0.0, min(float(height), y2)),
                )
                if box[2] <= box[0] or box[3] <= box[1]:
                    continue
                xywh = [int(box[0]), int(box[1]), int(box[2] - box[0]), int(box[3] - box[1])]
                candidates.setdefault(class_id, []).append((xywh, confidence, box))

            detections: list[Detection] = []
            for class_id, values in candidates.items():
                indices = cv2.dnn.NMSBoxes(
                    [item[0] for item in values],
                    [item[1] for item in values],
                    self.confidence,
                    0.45,
                )
                for index in np.asarray(indices).reshape(-1).tolist() if len(indices) else []:
                    _, confidence, box = values[int(index)]
                    detections.append(
                        Detection(class_id, self._class_names[class_id], confidence, box)
                    )
            return detections
        except Exception as exc:
            raise InferenceError("YOLO ONNX inference failed for the current frame") from exc
