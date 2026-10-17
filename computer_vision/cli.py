import argparse
import json
from pathlib import Path

from .backend_client import BackendEventClient
from .pipeline import SafetyVisionPipeline, VisionConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local Smart Safety Helmet YOLO inference")
    parser.add_argument("--config", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", type=Path)
    source.add_argument("--video", type=Path)
    source.add_argument("--webcam", type=int)
    source.add_argument("--rtsp")
    parser.add_argument("--backend-url", help="Optional API root, e.g. http://127.0.0.1:8000")
    args = parser.parse_args()

    config = VisionConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    pipeline = SafetyVisionPipeline.from_config(config)
    frames = (
        [pipeline.process_image(args.image)]
        if args.image
        else pipeline.iter_recorded_video(args.video)
        if args.video
        else pipeline.iter_webcam(args.webcam)
        if args.webcam is not None
        else pipeline.iter_rtsp(args.rtsp)
    )
    client = BackendEventClient(args.backend_url) if args.backend_url else None
    for result in frames:
        record = {
            "frame_index": result.frame_index,
            "inference_ms": round(result.inference_ms, 3),
            "detections": [d.__dict__ for d in result.detections],
            "events": [entry.event.model_dump(mode="json") for entry in result.zone_entries],
        }
        print(json.dumps(record))
        if client:
            for entry in result.zone_entries:
                client.send(entry.event)


if __name__ == "__main__":
    main()
