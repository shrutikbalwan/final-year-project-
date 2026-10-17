# PPE detector sample evaluation

Date: 2026-10-16

## Licence and attribution review

The evaluation images come from the `keremberke/hard-hat-detection` dataset on
Hugging Face, which identifies the dataset license as CC BY 4.0 and links the
Roboflow Hard Hats dataset source. CC BY 4.0 permits sharing and adaptation,
including commercial use, when attribution and a license link are provided.
This project used six images from the dataset's `test` split without editing
the image pixels; it converted the supplied box coordinates from `[x, y, width,
height]` to `[x1, y1, x2, y2]` for the evaluator. [Dataset card and license](https://huggingface.co/datasets/keremberke/hard-hat-detection),
[Roboflow source](https://universe.roboflow.com/roboflow-universe-projects/hard-hats-fhbh5/dataset/2),
[CC BY 4.0 terms](https://creativecommons.org/licenses/by/4.0/).

The model is `Hexmon/vyra-yolo-ppe-detection`, pinned at revision
`08895b33d95d2587423ebe4f7c1b9c41beebd642`. Its model card declares CC BY 4.0
and attributes its training data to Roboflow's PPE Combined Model v4. The
checkpoint file used was the repository's `best.onnx` (SHA-256
`b99fed37bae1d111ddb622a0ef9077d42918a4daebd4a0bffbd8faaba273f246`). The model
author and dataset attribution are retained here; no model or images are
redistributed in this repository. [Model card and license](https://huggingface.co/Hexmon/vyra-yolo-ppe-detection/tree/08895b33d95d2587423ebe4f7c1b9c41beebd642),
[CC BY 4.0 terms](https://creativecommons.org/licenses/by/4.0/).

The model card lists 14 classes. This evaluation explicitly filtered to
`Hardhat` and `NO-Hardhat`; it makes no claim about `Fall-Detected`, other PPE,
or compliance. Images and weights are held in ignored local directories under
`computer-vision/datasets/` and `computer-vision/models/`; no identifiable
footage was uploaded or embedded in the report.

## Method

- Model: the pinned YOLOv8m ONNX checkpoint above, run locally through OpenCV
  DNN on CPU; no Ultralytics Python package was needed for inference.
- Data: first six records of the dataset's test split, 640 × 640 images, with
  the source labels `hardhat` (compliant example) and `no-hardhat` (unsafe
  example). Three images of each label were included.
- Matching: same class name (case-insensitive) and intersection-over-union
  (IoU) of at least 0.50. Confidence threshold: 0.25.
- The selection was a small smoke/evaluation sample, not a random sample or a
  site-representative validation set.

## Results

| Test image ID | Ground truth | Correct detections (TP) | False positives (FP) | Missed boxes (FN) |
| --- | --- | ---: | ---: | ---: |
| 1617 | no-hardhat × 1 | 1 | 0 | 0 |
| 458 | no-hardhat × 6 | 6 | 0 | 0 |
| 1708 | no-hardhat × 3 | 3 | 0 | 0 |
| 160 | hardhat × 1 | 1 | 0 | 0 |
| 258 | hardhat × 2 | 2 | 0 | 0 |
| 449 | hardhat × 7 | 6 | 0 | 1 |
| **Total** | **20 boxes** | **19** | **0** | **1** |

- Precision: **1.00** (19 / 19 predicted boxes matched).
- Recall: **0.95** (19 / 20 labeled boxes matched).
- Mean inference time: **482.90 ms/image** for this run on the local CPU.
- IoU threshold: **0.50**.
- Missed detection: one `hardhat` box in image ID `449`, label box
  `[543, 202, 571, 263.5]` in `[x1, y1, x2, y2]` coordinates.
- False positives: none in these six images. This small sample cannot establish
  a reliable false-positive rate, especially for images with no labeled PPE.

The reported precision and recall are arithmetic for this six-image subset,
not a claim of general accuracy. It is too small and too narrow to validate
industrial use; a larger, independently selected dataset and target-camera
footage with permission are needed before making a deployment claim. The
measured CPU timing is also a per-image sample, not a performance guarantee.

### Repeat run recorded 2026-10-17

The same six-image manifest, model, selected classes, confidence threshold
(0.25), and IoU threshold (0.50) were evaluated again on the local CPU. The
repeat produced the same counts: 19 TP, 0 FP, and 1 FN, with precision 1.00 and
recall 0.95. Mean inference time was **561.41 ms/image** in that run. The earlier
run measured 482.90 ms/image; per-image timings varied between runs. These are
small local inference samples, not a camera stream, hardware, or deployment
benchmark. Keep the run-specific timings separate rather than treating either
as a stable performance guarantee.

## Reproduction on Windows PowerShell

Download the six sample images from the public dataset server and the pinned
ONNX checkpoint into the ignored local directories, from the repository root:

```powershell
$sampleDir = ".\computer-vision\datasets\hardhat-evaluation"
New-Item -ItemType Directory -Force $sampleDir, ".\computer-vision\models" | Out-Null
$rows = Invoke-RestMethod "https://datasets-server.huggingface.co/rows?dataset=keremberke%2Fhard-hat-detection&config=full&split=test&offset=0&length=6"
$images = @()
foreach ($entry in $rows.rows) {
  $r = $entry.row
  $name = "test-row-{0:D4}-image-{1}.jpg" -f $entry.row_idx, $r.image_id
  Invoke-WebRequest -Uri $r.image.src -OutFile (Join-Path $sampleDir $name)
  $labels = @()
  for ($i = 0; $i -lt $r.objects.category.Count; $i++) {
    $b = $r.objects.bbox[$i]
    $className = if ($r.objects.category[$i] -eq 0) { "hardhat" } else { "no-hardhat" }
    $labels += [pscustomobject]@{ class_name = $className; bbox_xyxy = @([double]$b[0], [double]$b[1], [double]($b[0] + $b[2]), [double]($b[1] + $b[3])) }
  }
  $images += [pscustomobject]@{ image_path = $name; ground_truth = $labels }
}
[pscustomobject]@{ images = $images } | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $sampleDir "manifest.json")
Invoke-WebRequest -Uri "https://huggingface.co/Hexmon/vyra-yolo-ppe-detection/resolve/08895b33d95d2587423ebe4f7c1b9c41beebd642/best.onnx?download=true" -OutFile ".\computer-vision\models\vyra-yolo-ppe-detection-best.onnx"
```

Then verify the checkpoint hash:

```powershell
Get-FileHash -Algorithm SHA256 .\computer-vision\models\vyra-yolo-ppe-detection-best.onnx
```

It should be `B99FED37BAE1D111DDB622A0EF9077D42918A4DAEBD4A0BFFBD8FAABA273F246`.
Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m computer_vision.evaluate_dataset `
  .\computer-vision\datasets\hardhat-evaluation\manifest.json `
  --weights .\computer-vision\models\vyra-yolo-ppe-detection-best.onnx `
  --model-class-names Fall-Detected Gloves Goggles Hardhat Ladder Mask `
    NO-Gloves NO-Goggles NO-Hardhat NO-Mask "NO-Safety Vest" Person `
    "Safety Cone" "Safety Vest" `
  --classes Hardhat NO-Hardhat `
  --output .\computer-vision\runs\hardhat-evaluation.json
```

The command prints aggregate precision, recall, false positives, false
negatives, mean inference time, and per-image missed/false-positive boxes. The
JSON output is also written to the ignored local `computer-vision/runs/` folder.
