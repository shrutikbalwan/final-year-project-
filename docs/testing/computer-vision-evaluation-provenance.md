# Hardhat detector benchmark: pinned test-split evaluation

## Result classification

This is a **potentially overlapping benchmark**, not an independent test. The
model card for the detector names Roboflow PPE Combined Model v4 as training
data. Although the evaluated Hard Hats dataset is a separate Roboflow project,
the published materials available for this run do not provide item-level
lineage sufficient to rule out shared images. The reported metrics therefore
must not be treated as independent generalization evidence, industrial PPE
compliance, or safety certification. They cover only `Hardhat` and
`NO-Hardhat` in this dataset.

## Dataset provenance and acquisition record

- Hugging Face dataset: [`keremberke/hard-hat-detection`](https://huggingface.co/datasets/keremberke/hard-hat-detection)
- Pinned revision: `694c61350faf9a6622586d6cf50f45e1631862dc`
- Acquired file: `data/test.zip`
- Exact source URL:
  `https://huggingface.co/datasets/keremberke/hard-hat-detection/resolve/694c61350faf9a6622586d6cf50f45e1631862dc/data/test.zip`
- Declared dataset-card licence: CC BY 4.0; attribution: “Hard Hats dataset by
  Roboflow Universe Projects,” source project
  <https://universe.roboflow.com/roboflow-universe-projects/hard-hats-fhbh5/dataset/2>.
  The declared licence and attribution are recorded from the dataset card; the
  archive itself was not executed.
- Retrieved: `2026-10-17T06:12:11.8820625Z`
- Archive size: `114425180` bytes
- Archive SHA-256:
  `e21ca22f4d69411af6e7c00b6d00ea30252867ac2d0f7cbef894b6ba9b9204c3`
- The response identified the same repository revision and linked size.
- The private archive and extracted images are under
  `computer-vision/private-datasets/` and are Git-ignored. The report contains
  metrics and source filenames, not image content.

Archive inspection found 2,002 entries: 2,001 JPEG images and one COCO JSON
annotation file. Compressed size was 114,052,466 bytes and declared extracted
size 115,620,142 bytes. Entries were flat, with no traversal paths, symbolic
links, executable entries, duplicate basenames, or unexpected file types.
The ZIP CRC check passed. Annotation validation found 2,001 unique image IDs,
5,518 unique annotation IDs, 27 images without labels, no missing image or
annotation references, no duplicate IDs, no invalid or out-of-bounds boxes,
and no dimension mismatches. All images are 640×640.

COCO category `0` (`hardhat`) maps to model class `Hardhat`; category `1`
(`no-hardhat`) maps to `NO-Hardhat`. COCO `[x, y, width, height]` boxes are
converted to `[x_min, y_min, x_max, y_max]`. Counts are 4,480 Hardhat and
1,038 NO-Hardhat boxes. The 27 images with no annotations remain in evaluation
as negative images; no labels were invented or records silently removed.

## Detector and evaluation method

- Architecture: YOLOv8m exported to ONNX.
- Model: `computer-vision/models/vyra-yolo-ppe-detection-best.onnx`
- Model SHA-256: `b99fed37bae1d111ddb622a0ef9077d42918a4daebd4a0bffbd8faaba273f246`
- Model source: `Hexmon/vyra-yolo-ppe-detection`, revision
  `08895b33d95d2587423ebe4f7c1b9c41beebd642`.
- Runtime: OpenCV DNN CPU; Python 3.13.15, OpenCV 4.14.0, NumPy 2.5.4,
  Windows 11 build `10.0.26300`, Intel64 Family 6 Model 141 Stepping 1.
- Evaluation confidence threshold: `0.25`; IoU threshold: `0.50`. These were
  fixed before evaluating the pinned test split and were not tuned on it.
- Matching: deterministic descending-confidence greedy, one-to-one and
  same-class. Each prediction chooses the still-unmatched same-class truth box
  with highest IoU; it is a TP at IoU ≥ 0.50, otherwise an FP. Unmatched truth
  boxes are FNs. Ties use class and box coordinates for stable ordering.
- Precision = TP/(TP+FP), recall = TP/(TP+FN), F1 is the harmonic mean.
  Zero-denominator metrics are defined as 0.0.
- Object-level TP/FP/FN and precision/recall/F1 are reported per class and
  micro-aggregated. Detection boxes have no finite background true-negative
  count, so FPR is separately defined here as **image-class FPR**: negative
  image/class pairs with at least one unmatched predicted box of that class,
  divided by all image/class pairs with no ground-truth box of that class.
  The pooled aggregate combines negative image-class pairs across both classes.
- Latency was measured on 100 deterministic images spread across the ordered
  test split: 10 warm-up calls, then 3 timed calls per image (300 calls total).
  The timed scope is detector inference only. It excludes dataset access, image
  decoding and metric matching. This is local CPU inference latency, not
  end-to-end camera throughput.

## Actual benchmark results

All 2,001 test images were evaluated. Full metrics, the per-image mapping,
every false-positive detection, and every missed ground-truth box are in
[`computer-vision-evaluation-results.json`](computer-vision-evaluation-results.json).

| Class | TP | FP | FN | Precision | Recall | F1 | Image-class FPR |
|---|---:|---:|---:|---:|---:|---:|---:|
| Hardhat | 4,032 | 427 | 448 | 0.9042 | 0.9000 | 0.9021 | 0.0080 (3/375) |
| NO-Hardhat | 777 | 69 | 261 | 0.9184 | 0.7486 | 0.8248 | 0.0107 (17/1,588) |
| Micro aggregate | 4,809 | 496 | 709 | 0.9065 | 0.8715 | 0.8887 | 0.0102 (20/1,963) |

Aggregate image-class FPR is not derived from object-level FP count. There were
496 false-positive boxes and 709 missed labelled boxes across the evaluated
images. These counts, per-image IDs and box coordinates are retained in the
machine-readable results.

Latency for the 300 timed CPU inference calls: mean 448.74 ms, median 428.52
ms, p95 579.97 ms, minimum 382.55 ms, maximum 763.42 ms. No GPU was used.
These timings are specific to the recorded machine/software and workload.

## Reproduction

The downloaded archive is intentionally not committed. After obtaining the
same pinned archive and verifying its SHA-256, prepare the local evaluation
manifest (the preparation command refuses a revision/hash/size mismatch and
validates archive paths, entries, CRC and COCO annotations):

```powershell
.\.venv\Scripts\python.exe -m computer_vision.prepare_coco_evaluation `
  --archive .\computer-vision\private-datasets\hard-hat-detection\test.zip `
  --output .\computer-vision\private-datasets\hard-hat-detection\evaluation-validated
```

Then run the evaluator with the documented model classes and fixed settings:

```powershell
.\.venv\Scripts\python.exe -m computer_vision.evaluate_dataset `
  .\computer-vision\private-datasets\hard-hat-detection\evaluation-validated\manifest.json `
  --weights .\computer-vision\models\vyra-yolo-ppe-detection-best.onnx `
  --model-class-names Fall-Detected Gloves Goggles Hardhat Ladder Mask `
    NO-Gloves NO-Goggles NO-Hardhat NO-Mask "NO-Safety Vest" Person `
    "Safety Cone" "Safety Vest" `
  --classes Hardhat NO-Hardhat --confidence 0.25 --iou 0.50 `
  --latency-warmup 10 --latency-repeats 3 --latency-images 100 `
  --output .\computer-vision\runs\hardhat-evaluation.json
```

Record the new run's model hash, dataset archive hash and runtime metadata; do
not overwrite the committed result record when comparing a new environment.

## Interpretation and limitations

The test split is fixed and was not used to tune the thresholds, but possible
training/test image overlap remains unresolved. Dataset source quality,
annotation consistency, acquisition conditions and the model's training data
may limit interpretation. Only the two named classes were scored; this report
does not validate any of the detector's other output classes, PPE compliance,
worker safety, other sites/cameras, or industrial deployment. Detections are
computer-vision events for review and are not safety-engine decisions.
