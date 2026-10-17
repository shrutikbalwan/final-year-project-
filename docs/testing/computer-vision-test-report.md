# Computer vision test report

Date: 2026-10-16

## Automated checks

Command run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Result:

```text
..............................................................           [100%]
62 passed in 2.14s
```

`git diff --check` also completed without whitespace errors. Both module help
commands were checked successfully:

```powershell
.\.venv\Scripts\python.exe -m computer_vision.cli --help
.\.venv\Scripts\python.exe -m computer_vision.evaluate_dataset --help
```

Tests use generated synthetic images and a temporary synthetic video, plus a
detector double. They exercise event conversion, class filtering, restricted
zone entry/re-entry, invalid image and video handling, unavailable webcam,
missing YOLO dependency/weights, evaluation metric arithmetic, and backend
delivery retry/idempotency. Backend API tests cover the shared event contract,
storage, duplicates, and invalid payloads.

## Evaluation status and limits

No Ultralytics/PyTorch model package, PPE weights, or labeled image set was
available in this environment. Therefore the automated run did not execute real
YOLO inference, and it does not establish PPE precision, recall, false-positive
rate, or real-time speed. The metric implementation is tested with synthetic
labels only. Run `computer_vision.evaluate_dataset` against a representative,
held-out, properly licensed labeled dataset and locally obtained compatible
weights before reporting model metrics. No training or fine-tuning was done.

The generic COCO model does not provide helmet/vest classes; the configured
class names must be present in the selected model's metadata. The implementation
does not claim detection of fire, smoke, falls, fatigue, or all PPE. Camera and
RTSP hardware operation was not exercised in this test environment.
