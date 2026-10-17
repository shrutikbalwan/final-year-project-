"""Deterministic object-detection evaluation for labeled still images."""

from dataclasses import dataclass
import math
from pathlib import Path
from statistics import fmean, median
from typing import Any, Callable

import cv2
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .detector import Detection
from .errors import InvalidImageError
from .pipeline import SafetyVisionPipeline


class LabeledBox(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    class_name: str = Field(min_length=1)
    bbox_xyxy: tuple[float, float, float, float]

    @field_validator("bbox_xyxy")
    @classmethod
    def valid_box(cls, box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        if not all(math.isfinite(value) for value in box):
            raise ValueError("bounding box coordinates must be finite")
        x1, y1, x2, y2 = box
        if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
            raise ValueError("bounding box must have non-negative origin and positive area")
        return box


class LabeledImage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    image_path: Path
    image_id: str | int | None = None
    ground_truth: list[LabeledBox]


@dataclass(frozen=True)
class ClassMetrics:
    class_name: str
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    image_false_positive_rate: float
    negative_image_count: int
    false_positive_image_count: int


@dataclass(frozen=True)
class EvaluationMetrics:
    image_count: int
    classes: tuple[str, ...]
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    image_false_positive_rate: float
    negative_image_class_count: int
    false_positive_image_class_count: int
    confidence_threshold: float
    iou_threshold: float
    per_class: tuple[ClassMetrics, ...]
    per_image: tuple[dict[str, Any], ...]
    image_dimensions: tuple[tuple[str, int, int], ...]
    latency: dict[str, Any]


def intersection_over_union(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    """Return IoU for xyxy boxes; invalid/non-finite boxes are rejected."""
    for box in (first, second):
        if len(box) != 4 or not all(math.isfinite(value) for value in box):
            raise ValueError("bounding boxes must contain four finite coordinates")
        x1, y1, x2, y2 = box
        if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
            raise ValueError("bounding boxes must have non-negative origin and positive area")
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    intersection_width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    intersection_height = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = intersection_width * intersection_height
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union


def _rates(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _validate_detection(detection: Detection) -> None:
    if not detection.class_name or not math.isfinite(detection.confidence):
        raise ValueError("detections require a class name and finite confidence")
    if not 0 <= detection.confidence <= 1:
        raise ValueError("detection confidence must be between 0 and 1")
    intersection_over_union(detection.bbox_xyxy, detection.bbox_xyxy)


def _latency_summary(
    pipeline: SafetyVisionPipeline,
    samples: list[LabeledImage],
    *,
    warmup_count: int,
    repeat_count: int,
    sample_count: int,
    progress: Callable[[str], None] | None,
) -> dict[str, Any]:
    if warmup_count < 0 or repeat_count < 1 or sample_count < 1:
        raise ValueError("latency warmup must be non-negative; repeats and sample count must be positive")
    if not samples:
        return {"sample_count": 0, "warmup_count": warmup_count, "repeat_count": repeat_count,
                "mean_ms": None, "median_ms": None, "p95_ms": None, "min_ms": None, "max_ms": None,
                "sample_image_ids": []}

    count = min(len(samples), sample_count)
    if count == 1:
        indices = [0]
    else:
        indices = [round(index * (len(samples) - 1) / (count - 1)) for index in range(count)]
    selected = [samples[index] for index in indices]
    for index in range(warmup_count):
        pipeline.process_image(selected[index % len(selected)].image_path)
    if progress:
        progress(f"latency warm-up complete: {warmup_count} inference(s)")

    timings: list[float] = []
    for repeat in range(repeat_count):
        for sample_index, sample in enumerate(selected):
            timings.append(pipeline.process_image(sample.image_path).inference_ms)
        if progress:
            progress(f"latency repeat {repeat + 1}/{repeat_count} complete")
    ordered = sorted(timings)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "sample_count": len(timings),
        "warmup_count": warmup_count,
        "repeat_count": repeat_count,
        "latency_image_count": len(selected),
        "mean_ms": fmean(timings),
        "median_ms": median(timings),
        "p95_ms": ordered[p95_index],
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
        "sample_image_ids": [sample.image_id if sample.image_id is not None else sample.image_path.name
                              for sample in selected],
        "timed_scope": "detector call only; excludes dataset access, image decode, and evaluation matching",
    }


def evaluate_labeled_images(
    pipeline: SafetyVisionPipeline,
    samples: list[LabeledImage],
    *,
    classes: list[str],
    confidence_threshold: float = 0.25,
    iou_threshold: float = 0.5,
    latency_warmup: int = 10,
    latency_repeats: int = 3,
    latency_image_count: int = 100,
    progress: Callable[[str], None] | None = None,
) -> EvaluationMetrics:
    if not 0 < confidence_threshold <= 1:
        raise ValueError("confidence_threshold must be greater than 0 and at most 1")
    if not 0 < iou_threshold <= 1:
        raise ValueError("iou_threshold must be greater than 0 and at most 1")
    normalized_classes = [name.casefold() for name in classes]
    if not classes or any(not name.strip() for name in classes) or len(set(normalized_classes)) != len(classes):
        raise ValueError("classes must contain unique, non-empty names")

    counts = {name: {"tp": 0, "fp": 0, "fn": 0, "negative_images": 0,
                     "false_positive_images": 0} for name in classes}
    image_results: list[dict[str, Any]] = []
    image_dimensions: list[tuple[str, int, int]] = []
    total_tp = total_fp = total_fn = 0
    total_negative_image_classes = total_false_positive_image_classes = 0

    for sample_index, sample in enumerate(samples, start=1):
        frame = cv2.imread(str(sample.image_path))
        if frame is None:
            raise InvalidImageError(f"Could not load image: {sample.image_path}")
        height, width = frame.shape[:2]
        allowed = set(normalized_classes)
        for label in sample.ground_truth:
            if label.class_name.casefold() not in allowed:
                raise ValueError(f"ground-truth class is outside evaluation classes: {label.class_name}")
            if label.bbox_xyxy[2] > width or label.bbox_xyxy[3] > height:
                raise ValueError(f"ground-truth box exceeds image dimensions: {sample.image_path}")
        image_id = sample.image_id if sample.image_id is not None else sample.image_path.name
        image_dimensions.append((str(image_id), width, height))
        result = pipeline.process_frame(frame, 0)
        detections = [item for item in result.detections if item.confidence >= confidence_threshold]
        for detection in detections:
            _validate_detection(detection)
            if detection.bbox_xyxy[2] > width or detection.bbox_xyxy[3] > height:
                raise ValueError(f"predicted box exceeds image dimensions: {sample.image_path}")

        sample_gt_classes = {box.class_name.casefold() for box in sample.ground_truth}
        image_used: dict[str, set[int]] = {name.casefold(): set() for name in classes}
        image_tp: dict[str, int] = {name: 0 for name in classes}
        image_fp: dict[str, int] = {name: 0 for name in classes}
        image_fn: dict[str, int] = {name: 0 for name in classes}
        missed: list[dict[str, Any]] = []
        false_positives: list[dict[str, Any]] = []

        for detection in sorted(detections, key=lambda item: (-item.confidence, item.class_id,
                                                               item.bbox_xyxy)):
            class_index = next((i for i, name in enumerate(normalized_classes)
                                if name == detection.class_name.casefold()), None)
            if class_index is None:
                continue
            class_key = normalized_classes[class_index]
            class_name = classes[class_index]
            candidates = [
                (index, label)
                for index, label in enumerate(sample.ground_truth)
                if label.class_name.casefold() == class_key and index not in image_used[class_key]
            ]
            best = max(candidates, key=lambda pair: (intersection_over_union(
                detection.bbox_xyxy, pair[1].bbox_xyxy), -pair[0]), default=None)
            if best and intersection_over_union(detection.bbox_xyxy, best[1].bbox_xyxy) >= iou_threshold:
                image_used[class_key].add(best[0])
                image_tp[class_name] += 1
            else:
                image_fp[class_name] += 1
                false_positives.append({"class_name": detection.class_name, "confidence": detection.confidence,
                                        "bbox_xyxy": list(detection.bbox_xyxy)})

        for index, label in enumerate(sample.ground_truth):
            class_index = next((i for i, name in enumerate(normalized_classes)
                                if name == label.class_name.casefold()), None)
            if class_index is None:
                continue
            class_name = classes[class_index]
            if index not in image_used[normalized_classes[class_index]]:
                image_fn[class_name] += 1
                missed.append({"class_name": label.class_name, "bbox_xyxy": list(label.bbox_xyxy)})

        for class_name in classes:
            values = counts[class_name]
            values["tp"] += image_tp[class_name]
            values["fp"] += image_fp[class_name]
            values["fn"] += image_fn[class_name]
            if class_name.casefold() not in sample_gt_classes:
                values["negative_images"] += 1
                total_negative_image_classes += 1
                if image_fp[class_name]:
                    values["false_positive_images"] += 1
                    total_false_positive_image_classes += 1
        item_tp, item_fp, item_fn = sum(image_tp.values()), sum(image_fp.values()), sum(image_fn.values())
        total_tp += item_tp
        total_fp += item_fp
        total_fn += item_fn
        image_results.append({
            "image_id": image_id,
            "image_path": str(sample.image_path),
            "width": width,
            "height": height,
            "true_positives": item_tp,
            "false_positives": item_fp,
            "false_negatives": item_fn,
            "missed_ground_truth": missed,
            "false_positive_detections": false_positives,
            "per_class": {name: {"true_positives": image_tp[name], "false_positives": image_fp[name],
                                  "false_negatives": image_fn[name]} for name in classes},
        })
        if progress and (sample_index % 100 == 0 or sample_index == len(samples)):
            progress(f"accuracy evaluation: {sample_index}/{len(samples)} images")

    precision, recall, f1 = _rates(total_tp, total_fp, total_fn)
    per_class: list[ClassMetrics] = []
    for name in classes:
        values = counts[name]
        class_precision, class_recall, class_f1 = _rates(values["tp"], values["fp"], values["fn"])
        per_class.append(ClassMetrics(
            class_name=name,
            true_positives=values["tp"],
            false_positives=values["fp"],
            false_negatives=values["fn"],
            precision=class_precision,
            recall=class_recall,
            f1=class_f1,
            image_false_positive_rate=(values["false_positive_images"] / values["negative_images"]
                                       if values["negative_images"] else 0.0),
            negative_image_count=values["negative_images"],
            false_positive_image_count=values["false_positive_images"],
        ))

    return EvaluationMetrics(
        image_count=len(samples),
        classes=tuple(classes),
        true_positives=total_tp,
        false_positives=total_fp,
        false_negatives=total_fn,
        precision=precision,
        recall=recall,
        f1=f1,
        image_false_positive_rate=(total_false_positive_image_classes / total_negative_image_classes
                                   if total_negative_image_classes else 0.0),
        negative_image_class_count=total_negative_image_classes,
        false_positive_image_class_count=total_false_positive_image_classes,
        confidence_threshold=confidence_threshold,
        iou_threshold=iou_threshold,
        per_class=tuple(per_class),
        per_image=tuple(image_results),
        image_dimensions=tuple(image_dimensions),
        latency=_latency_summary(pipeline, samples, warmup_count=latency_warmup,
                                 repeat_count=latency_repeats, sample_count=latency_image_count,
                                 progress=progress),
    )
