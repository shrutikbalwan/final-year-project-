from pathlib import Path

import cv2
import numpy as np
import pytest

from computer_vision.detector import Detection
from computer_vision.backend_client import BackendDeliveryError, BackendEventClient
from computer_vision.errors import InvalidImageError, ModelLoadError, UnsupportedClassError, VideoSourceError
from computer_vision.evaluation import LabeledBox, LabeledImage, evaluate_labeled_images
from computer_vision.pipeline import RestrictedZone, SafetyVisionPipeline, VisionConfig


class SyntheticDetector:
    class_names = {0: "person", 1: "hardhat"}

    def __init__(self, outputs=None):
        self.outputs = list([[Detection(0, "person", 0.91, (10, 10, 30, 30), 17)]] if outputs is None else outputs)
        self.track_calls = []

    def detect(self, frame, *, track=False):
        self.track_calls.append(track)
        if len(self.outputs) > 1:
            return self.outputs.pop(0)
        return self.outputs[0]


def config(**changes):
    values = {
        "camera_id": "synthetic-camera-001",
        "workplace_id": "synthetic-workplace-001",
    }
    values.update(changes)
    return VisionConfig.model_validate(values)


def synthetic_image(path: Path):
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    assert cv2.imwrite(str(path), image)
    return path


def test_processes_image_with_supported_model_classes_and_timing(tmp_path):
    detector = SyntheticDetector()
    pipeline = SafetyVisionPipeline(config(), detector)
    result = pipeline.process_image(synthetic_image(tmp_path / "synthetic-frame.png"))

    assert result.frame_index == 0
    assert result.inference_ms >= 0
    assert result.detections[0].class_name == "person"
    assert result.zone_entries == ()


def test_requested_classes_must_exist_in_selected_model():
    with pytest.raises(UnsupportedClassError, match="does not support"):
        SafetyVisionPipeline(config(requested_classes=["smoke"]), SyntheticDetector())

    pipeline = SafetyVisionPipeline(config(requested_classes=["hardhat"]), SyntheticDetector())
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    assert pipeline.process_frame(frame).detections == ()

    zone = RestrictedZone(zone_id="synthetic-zone", polygon=[(0, 0), (1, 0), (1, 1)])
    with pytest.raises(UnsupportedClassError, match="must include a supported person"):
        SafetyVisionPipeline(
            config(requested_classes=["hardhat"], restricted_zones=[zone]),
            SyntheticDetector(),
        )


def test_restricted_zone_uses_person_tracking_and_emits_contract_event():
    detector = SyntheticDetector(
        [
            [Detection(0, "person", 0.9, (10, 10, 30, 30), 17)],
            [Detection(0, "person", 0.9, (10, 10, 30, 30), 17)],
            [Detection(0, "person", 0.9, (40, 30, 55, 45), 17)],
            [Detection(0, "person", 0.9, (10, 10, 30, 30), 17)],
        ]
    )
    zone = RestrictedZone(zone_id="synthetic-zone-1", polygon=[(0, 0), (0.6, 0), (0.6, 0.7), (0, 0.7)])
    pipeline = SafetyVisionPipeline(config(restricted_zones=[zone]), detector)
    frame = np.zeros((48, 64, 3), dtype=np.uint8)

    first = pipeline.process_frame(frame, 1)
    repeated_inside = pipeline.process_frame(frame, 2)
    outside = pipeline.process_frame(frame, 3)
    reentered = pipeline.process_frame(frame, 4)

    assert len(first.zone_entries) == 1
    assert repeated_inside.zone_entries == ()
    assert outside.zone_entries == ()
    assert len(reentered.zone_entries) == 1
    event = first.zone_entries[0].event
    assert event.event_type == "hazard_detected"
    assert event.severity == "unknown"
    assert event.device_id == "synthetic-camera-001"
    assert event.workplace_id == "synthetic-workplace-001"
    assert "synthetic-zone-1" in event.description
    assert all(detector.track_calls)


def test_processes_recorded_video_without_retaining_frames(tmp_path):
    video_path = tmp_path / "synthetic-video.avi"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 5, (64, 48))
    assert writer.isOpened()
    for _ in range(3):
        writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    writer.release()

    results = list(SafetyVisionPipeline(config(), SyntheticDetector()).iter_video(video_path))

    assert len(results) == 3
    assert [result.frame_index for result in results] == [0, 1, 2]
    assert all(result.inference_ms >= 0 for result in results)
    assert all(not hasattr(result, "frame") for result in results)


def test_unavailable_webcam_or_invalid_video_source_raises(tmp_path):
    pipeline = SafetyVisionPipeline(config(), SyntheticDetector())
    with pytest.raises(VideoSourceError, match="Could not open"):
        list(pipeline.iter_video(9876))
    with pytest.raises(VideoSourceError, match="Could not open"):
        list(pipeline.iter_video(tmp_path / "missing-video.mp4"))


def test_unreadable_image_raises(tmp_path):
    pipeline = SafetyVisionPipeline(config(), SyntheticDetector())
    with pytest.raises(InvalidImageError):
        pipeline.process_image(tmp_path / "missing-image.png")


def test_missing_ultralytics_or_weights_has_actionable_error(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "ultralytics", None)
    with pytest.raises(ModelLoadError, match="Install requirements-cv"):
        SafetyVisionPipeline(config())


def test_opencv_onnx_detector_decodes_configured_yolo_classes(monkeypatch):
    import cv2
    import numpy as np

    class FakeNet:
        def setInput(self, blob):
            self.blob = blob

        def forward(self):
            return np.array([[[320.0], [320.0], [100.0], [100.0], [0.9], [0.1]]])

    monkeypatch.setattr(cv2.dnn, "readNetFromONNX", lambda _path: FakeNet())
    from computer_vision.detector import UltralyticsYoloDetector

    detector = UltralyticsYoloDetector(
        "synthetic.onnx", confidence=0.25, class_names=["hardhat", "no-hardhat"]
    )
    detections = detector.detect(np.zeros((640, 640, 3), dtype=np.uint8))

    assert len(detections) == 1
    assert detections[0].class_name == "hardhat"
    assert detections[0].bbox_xyxy == pytest.approx((270, 270, 370, 370))


def test_labeled_image_evaluation_reports_precision_recall_fp_and_latency(tmp_path):
    first = synthetic_image(tmp_path / "synthetic-labeled-1.png")
    second = synthetic_image(tmp_path / "synthetic-labeled-2.png")
    third = synthetic_image(tmp_path / "synthetic-labeled-3.png")
    pipeline = SafetyVisionPipeline(config(), SyntheticDetector())
    samples = [
        LabeledImage(image_path=first, ground_truth=[LabeledBox(class_name="person", bbox_xyxy=(10, 10, 30, 30))]),
        LabeledImage(image_path=second, ground_truth=[]),
        LabeledImage(image_path=third, ground_truth=[LabeledBox(class_name="hardhat", bbox_xyxy=(12, 12, 20, 20))]),
    ]

    metrics = evaluate_labeled_images(
        pipeline, samples, classes=["person", "hardhat"], iou_threshold=0.5,
        latency_warmup=0, latency_repeats=1, latency_image_count=1,
    )

    assert metrics.image_count == 3
    assert metrics.true_positives == 1
    assert metrics.false_positives == 2
    assert metrics.false_negatives == 1
    assert metrics.precision == pytest.approx(1 / 3)
    assert metrics.recall == pytest.approx(0.5)
    assert metrics.latency["mean_ms"] >= 0
    assert metrics.per_image[0]["true_positives"] == 1
    assert metrics.per_image[1]["false_positives"] == 1
    assert metrics.per_image[2]["false_negatives"] == 1
    assert metrics.per_image[2]["missed_ground_truth"][0]["class_name"] == "hardhat"


def _evaluate(tmp_path, detections, labels, *, classes=("hardhat", "NO-Hardhat"), confidence=0.25, iou=0.5):
    image = synthetic_image(tmp_path / "synthetic-eval.png")
    pipeline = SafetyVisionPipeline(config(), SyntheticDetector([detections]))
    sample = LabeledImage(image_path=image, image_id=7, ground_truth=labels)
    return evaluate_labeled_images(
        pipeline, [sample], classes=list(classes), confidence_threshold=confidence,
        iou_threshold=iou, latency_warmup=0, latency_repeats=1, latency_image_count=1,
    )


def test_evaluation_same_class_matches_wrong_class_is_false_positive(tmp_path):
    metrics = _evaluate(
        tmp_path,
        [Detection(1, "hardhat", 0.8, (10, 10, 30, 30)),
         Detection(2, "NO-Hardhat", 0.9, (10, 10, 30, 30))],
        [LabeledBox(class_name="Hardhat", bbox_xyxy=(10, 10, 30, 30))],
    )
    assert (metrics.true_positives, metrics.false_positives, metrics.false_negatives) == (1, 1, 0)
    assert metrics.per_class[0].f1 == pytest.approx(1.0)
    assert metrics.per_class[1].false_positives == 1


def test_duplicate_detections_only_match_one_ground_truth(tmp_path):
    box = (10, 10, 30, 30)
    metrics = _evaluate(
        tmp_path,
        [Detection(1, "Hardhat", 0.9, box), Detection(1, "Hardhat", 0.8, box)],
        [LabeledBox(class_name="Hardhat", bbox_xyxy=box)],
        classes=("Hardhat",),
    )
    assert (metrics.true_positives, metrics.false_positives, metrics.false_negatives) == (1, 1, 0)
    assert metrics.per_image[0]["false_positive_detections"][0]["confidence"] == 0.8


def test_confidence_and_iou_threshold_boundaries_are_inclusive(tmp_path):
    metrics = _evaluate(
        tmp_path,
        [Detection(1, "Hardhat", 0.25, (10, 10, 30, 30))],
        [LabeledBox(class_name="Hardhat", bbox_xyxy=(10, 10, 20, 30))],
        classes=("Hardhat",), confidence=0.25, iou=0.5,
    )
    assert metrics.true_positives == 1
    assert metrics.false_positives == metrics.false_negatives == 0


def test_empty_predictions_and_ground_truth_have_defined_zero_denominators(tmp_path):
    no_predictions = _evaluate(tmp_path, [], [], classes=("Hardhat",))
    assert no_predictions.precision == no_predictions.recall == no_predictions.f1 == 0
    assert no_predictions.per_class[0].image_false_positive_rate == 0
    assert no_predictions.per_class[0].negative_image_count == 1

    missing = _evaluate(
        tmp_path, [], [LabeledBox(class_name="Hardhat", bbox_xyxy=(10, 10, 20, 20))],
        classes=("Hardhat",),
    )
    assert (missing.true_positives, missing.false_positives, missing.false_negatives) == (0, 0, 1)

    false_alarm = _evaluate(
        tmp_path, [Detection(1, "Hardhat", 0.9, (10, 10, 20, 20))], [], classes=("Hardhat",)
    )
    assert false_alarm.precision == 0
    assert false_alarm.per_class[0].image_false_positive_rate == 1


def test_per_class_and_aggregate_metrics_and_order_are_reproducible(tmp_path):
    metrics = _evaluate(
        tmp_path,
        [Detection(1, "NO-Hardhat", 0.9, (10, 10, 20, 20)),
         Detection(1, "Hardhat", 0.9, (10, 10, 20, 20))],
        [LabeledBox(class_name="Hardhat", bbox_xyxy=(10, 10, 20, 20))],
        classes=("Hardhat", "NO-Hardhat"),
    )
    assert (metrics.true_positives, metrics.false_positives, metrics.false_negatives) == (1, 1, 0)
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.recall == pytest.approx(1.0)
    assert metrics.f1 == pytest.approx(2 / 3)
    assert [(item.class_name, item.false_positives) for item in metrics.per_class] == [
        ("Hardhat", 0), ("NO-Hardhat", 1)
    ]
    assert metrics.per_image[0]["image_id"] == 7
    assert [item["class_name"] for item in metrics.per_image[0]["false_positive_detections"]] == ["NO-Hardhat"]


def test_invalid_boxes_and_malformed_classes_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="positive area"):
        LabeledBox(class_name="Hardhat", bbox_xyxy=(10, 10, 10, 20))
    with pytest.raises(ValueError, match="finite"):
        LabeledBox(class_name="Hardhat", bbox_xyxy=(10, 10, float("nan"), 20))
    with pytest.raises(ValueError, match="outside evaluation classes"):
        _evaluate(tmp_path, [], [LabeledBox(class_name="person", bbox_xyxy=(1, 1, 5, 5))], classes=("Hardhat",))
    with pytest.raises(ValueError, match="exceeds image dimensions"):
        _evaluate(tmp_path, [], [LabeledBox(class_name="Hardhat", bbox_xyxy=(1, 1, 99, 40))], classes=("Hardhat",))


def test_invalid_predicted_box_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="positive area"):
        _evaluate(tmp_path, [Detection(1, "Hardhat", 0.9, (10, 10, 10, 20))], [], classes=("Hardhat",))


def test_iou_invalid_threshold_and_box_are_rejected():
    from computer_vision.evaluation import intersection_over_union

    with pytest.raises(ValueError, match="positive area"):
        intersection_over_union((1, 1, 1, 2), (0, 0, 2, 2))
    with pytest.raises(ValueError, match="iou_threshold"):
        evaluate_labeled_images(
            SafetyVisionPipeline(config(), SyntheticDetector()), [], classes=["person"], iou_threshold=0,
        )


def test_backend_client_retries_transient_failures_with_same_event(monkeypatch):
    from urllib.error import HTTPError
    from io import BytesIO

    event = SafetyVisionPipeline(
        config(
            restricted_zones=[
                RestrictedZone(
                    zone_id="synthetic-zone",
                    polygon=[(0, 0), (0.8, 0), (0.8, 0.8), (0, 0.8)],
                )
            ]
        ),
        SyntheticDetector(),
    ).process_frame(np.zeros((48, 64, 3), dtype=np.uint8)).zone_entries[0].event
    calls = []

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return event.model_dump_json().encode("utf-8")

    def fail_once(request, timeout):
        calls.append((request.data, request.get_header("Authorization")))
        if len(calls) == 1:
            raise HTTPError(request.full_url, 503, "temporary", {}, BytesIO())
        return Response()

    monkeypatch.setattr("computer_vision.backend_client.urlopen", fail_once)
    monkeypatch.setattr("computer_vision.backend_client.time.sleep", lambda _: None)
    returned = BackendEventClient("http://127.0.0.1:8000", max_attempts=2,
                                  bearer_token="synthetic-test-token").send(event)

    assert returned.event_id == event.event_id
    assert calls[0] == calls[1]
    assert calls[0][1] == "Bearer synthetic-test-token"


def test_backend_client_treats_duplicate_event_id_as_delivered(monkeypatch):
    from io import BytesIO
    from urllib.error import HTTPError

    event = SafetyVisionPipeline(config(), SyntheticDetector())._zone_event("synthetic-zone", 17).event

    def duplicate(request, timeout):
        raise HTTPError(request.full_url, 409, "duplicate", {}, BytesIO())

    monkeypatch.setattr("computer_vision.backend_client.urlopen", duplicate)
    assert BackendEventClient("http://127.0.0.1:8000").send(event) == event


def test_backend_client_surfaces_permanent_rejection(monkeypatch):
    from io import BytesIO
    from urllib.error import HTTPError

    event = SafetyVisionPipeline(config(), SyntheticDetector())._zone_event("synthetic-zone", 17).event

    def reject(request, timeout):
        raise HTTPError(request.full_url, 422, "invalid", {}, BytesIO())

    monkeypatch.setattr("computer_vision.backend_client.urlopen", reject)
    with pytest.raises(BackendDeliveryError, match="HTTP 422"):
        BackendEventClient("http://127.0.0.1:8000").send(event)
