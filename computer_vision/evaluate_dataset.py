"""Evaluate a pinned YOLO model against an explicitly versioned image manifest."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import sys

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .evaluation import LabeledImage, evaluate_labeled_images
from .pipeline import SafetyVisionPipeline, VisionConfig


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str = Field(min_length=1)
    dataset_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    dataset_license: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_size_bytes: int = Field(gt=0)
    retrieved_utc: str = Field(min_length=1)
    validation: dict
    classes: list[str] = Field(min_length=1)
    images: list[dict]

    @field_validator("classes")
    @classmethod
    def unique_classes(cls, values: list[str]) -> list[str]:
        folded = [value.casefold() for value in values]
        if any(not value.strip() for value in values) or len(set(folded)) != len(values):
            raise ValueError("classes must be unique non-empty names")
        return values


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a pinned YOLO model on labeled images")
    parser.add_argument("manifest", type=Path, help="versioned JSON manifest with image labels")
    parser.add_argument("--weights", required=True, type=Path, help="local model weights")
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.50)
    parser.add_argument("--latency-warmup", type=int, default=10)
    parser.add_argument("--latency-repeats", type=int, default=3)
    parser.add_argument("--latency-images", type=int, default=100,
                        help="deterministically sampled images used for latency only")
    parser.add_argument("--camera-id", default="evaluation-camera")
    parser.add_argument("--workplace-id", default="evaluation-workplace")
    parser.add_argument("--classes", nargs="+", default=["Hardhat", "NO-Hardhat"])
    parser.add_argument("--model-class-names", nargs="+", required=True,
                        help="ordered ONNX class names from the pinned model card")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest_raw = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    manifest = DatasetManifest.model_validate(manifest_raw)
    if [name.casefold() for name in args.classes] != [name.casefold() for name in manifest.classes]:
        parser.error("--classes must match the class order in the dataset manifest")
    image_records: list[LabeledImage] = []
    for item in manifest.images:
        record = dict(item)
        image_path = Path(record["image_path"])
        if not image_path.is_absolute():
            record["image_path"] = args.manifest.parent / image_path
        image_records.append(LabeledImage.model_validate(record))

    pipeline = SafetyVisionPipeline.from_config(VisionConfig(
        weights=str(args.weights),
        confidence=args.confidence,
        requested_classes=args.classes,
        model_class_names=args.model_class_names,
        camera_id=args.camera_id,
        workplace_id=args.workplace_id,
    ))
    metrics = evaluate_labeled_images(
        pipeline,
        image_records,
        classes=args.classes,
        confidence_threshold=args.confidence,
        iou_threshold=args.iou,
        latency_warmup=args.latency_warmup,
        latency_repeats=args.latency_repeats,
        latency_image_count=args.latency_images,
        progress=lambda message: print(message, file=sys.stderr, flush=True),
    )
    result = {
        "dataset": {
            "name": manifest.dataset,
            "revision": manifest.dataset_revision,
            "license": manifest.dataset_license,
            "attribution": manifest.attribution,
            "source_url": manifest.source_url,
            "archive_sha256": manifest.archive_sha256,
            "archive_size_bytes": manifest.archive_size_bytes,
            "retrieved_utc": manifest.retrieved_utc,
            "manifest_validation": manifest.validation,
        },
        "model": {
            "architecture": "YOLOv8m ONNX",
            "source_repo": "Hexmon/vyra-yolo-ppe-detection",
            "source_revision": "08895b33d95d2587423ebe4f7c1b9c41beebd642",
            "path": str(args.weights),
            "sha256": _sha256(args.weights),
            "classes": args.model_class_names,
        },
        "configuration": {
            "evaluated_classes": args.classes,
            "confidence_threshold": args.confidence,
            "iou_threshold": args.iou,
            "matching": "descending-confidence greedy one-to-one; same class; IoU >= threshold",
            "latency_warmup_count": args.latency_warmup,
            "latency_repeat_count": args.latency_repeats,
            "latency_image_count": args.latency_images,
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor() or platform.machine(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "inference_backend": "OpenCV DNN CPU" if args.weights.suffix.casefold() == ".onnx" else "configured Ultralytics device",
        },
        "limitations": [
            "Dataset/model training-data overlap has not been ruled out; treat as a potentially overlapping benchmark.",
            "Results cover only the evaluated classes and dataset; they are not PPE compliance or safety certification.",
        ],
        "metrics": asdict(metrics),
    }
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
