# Local computer vision

This module uses OpenCV for local image/video capture and Ultralytics YOLOv8 for
optional model inference. Frames are processed one at a time and are not saved
or streamed by the pipeline. Use only footage you are authorized to process.
Do not place recordings, weights, or private datasets in Git; these paths are
ignored by `.gitignore`.

## Install and configure

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cv.txt
Copy-Item .\computer-vision\config\vision.example.json .\computer-vision\config\vision.local.json
```

YOLO weights are not included. The Python default `yolov8n.pt` is the general
COCO model; Ultralytics may download it on first load. It detects general COCO
classes such as `person`, but COCO does not contain safety helmet/vest classes.
For PPE, point `weights` to a separately obtained PPE-trained model and list
only class names present in that model's metadata. The example config uses
illustrative `person`, `hardhat`, and `no-hardhat` names; it requires custom
weights that actually expose those names. Unsupported requested classes raise
an error. A detected helmet object is not by itself proof that a person is
wearing it; no compliance inference is implemented here.

The SHWD (Safety Helmet Wearing Dataset) is an appropriate helmet-focused
labelled dataset for an initial evaluation; its upstream description reports
`hat` and `person` labels and a substantial class imbalance. Review its upstream
data terms and the model/dataset licenses before use. It does not evaluate
restricted-zone behavior or prove performance at a particular site. [SHWD source](https://github.com/njvisionpower/Safety-Helmet-Wearing-Dataset).

## Run image, recorded video, webcam, or RTSP

```powershell
$config = ".\computer-vision\config\vision.local.json"
python -m computer_vision.cli --config $config --image .\sample.jpg
python -m computer_vision.cli --config $config --video .\sample.mp4
python -m computer_vision.cli --config $config --webcam 0
python -m computer_vision.cli --config $config --rtsp "rtsp://camera-host/stream"
```

The RTSP URL is an optional input interface; credentials should not be embedded
in URLs or committed. Webcam/RTSP requires a working local camera/network route.
Unavailable devices and malformed sources raise `VideoSourceError`; bad images,
missing optional YOLO dependencies, missing weights, and inference errors have
separate actionable errors. Inference runs on CPU by default. Set `device` only
to a device supported by the local Ultralytics/PyTorch installation.

Restricted zones are polygons in normalized frame coordinates (0 to 1). When a
tracked `person` enters a configured zone, the pipeline emits one event per
track entry. The `SafetyEvent` uses `hazard_detected`, severity `unknown`, and a
human-review description. It does not assign an industrial severity or assume
that a detection is a confirmed safety incident. Only detections from supported
model classes are returned; this module does not claim to detect fire, smoke,
falls, fatigue, or all PPE categories.

The CLI prints detection boxes, confidence, tracker IDs, frame number, and
inference time in milliseconds. It does not render or write annotated video.
Optional event delivery to the local backend:

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
python -m computer_vision.cli --config $config --video .\sample.mp4 --backend-url http://127.0.0.1:8000
```

The client posts the existing contract to `POST /api/v1/events`, retries
transient failures with the same event ID, and treats HTTP 409 as an already
accepted idempotent event. The local API requires a bearer token. Sign in at
`/api/v1/auth/login`, then set `HELMET_API_TOKEN` in the local process
environment before event delivery. The token expires; obtain a fresh token for
longer-running sessions. Keep the API on loopback and use managed device
identity before remote deployment.

## Labeled evaluation

`computer_vision.evaluation` matches predicted and labeled boxes by class and
IoU and reports per-class and aggregate TP/FP/FN, precision, recall, F1,
image-class false-positive rate, per-image misses and false positives, image
dimensions, and inference latency. Object detection has no finite background
true-negative count, so its documented false-positive rate is defined over
negative image/class pairs. `computer_vision.evaluate_dataset` requires a
versioned dataset manifest and accepts explicit `--confidence` and `--iou`
thresholds. Its timing protocol defaults to 10 warm-ups and 3 repeats on a
deterministic spread of up to 100 images; the reported timer covers the model
call only and excludes image decode and matching.

The pinned `keremberke/hard-hat-detection` test split was acquired and evaluated
as a potentially overlapping benchmark. Provenance, archive validation,
methodology, actual results, limitations, and exact PowerShell reproduction
commands are in the [evaluation report](../docs/testing/computer-vision-evaluation-provenance.md).
Machine-readable results retain per-image false positives and missed labels in
[`computer-vision-evaluation-results.json`](../docs/testing/computer-vision-evaluation-results.json).
The historical six-image figures remain a separate smoke sample and must not be
presented as representative results.

A manifest carries the pinned dataset revision and contains records like:

```json
{
  "dataset": "example-public-dataset",
  "dataset_revision": "0123456789abcdef0123456789abcdef01234567",
  "dataset_license": "license identifier",
  "attribution": "required dataset attribution",
  "classes": ["hat", "no-hat"],
  "images": [
    {
      "image_path": "private-datasets/shwd/images/example.jpg",
      "image_id": "example-001",
      "ground_truth": [
        {"class_name": "hat", "bbox_xyxy": [10, 20, 40, 60]}
      ]
    }
  ]
}
```

```powershell
python -m computer_vision.evaluate_dataset .\computer-vision\datasets\evaluation-manifest.json --weights .\computer-vision\models\ppe-model.pt
```

For an auditable small evaluation run, use a local copy of the CC BY 4.0
Hard Hats test split and a compatible PPE model. The model class names must come
from the model card; for an ONNX export, pass them in order with
`--model-class-names`. The JSON output includes missed ground-truth boxes and
false-positive detections per image. Keep the downloaded images and weights out
of Git; `computer-vision/datasets/` and `computer-vision/models/` are ignored.

The earlier six-image smoke sample and its historical measurements are recorded
in [docs/testing/computer-vision-evaluation.md](../docs/testing/computer-vision-evaluation.md).
They are not representative validation or certified/site-specific PPE results.
Keep test images local and avoid including identifiable footage in reports
unless approved.

## Tests

```powershell
python -m pytest -q
```

Tests create temporary synthetic image/video files and use a detector double;
they require no camera, model download, or worker footage.
