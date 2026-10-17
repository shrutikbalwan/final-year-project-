"""Safely validate and extract a COCO object-detection test archive."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat
from zipfile import ZipFile

import cv2


DATASET_NAME = "keremberke/hard-hat-detection"
DATASET_REVISION = "694c61350faf9a6622586d6cf50f45e1631862dc"
DATASET_LICENSE = "CC BY 4.0 (as declared by the dataset card)"
ATTRIBUTION = (
    "Hard Hats dataset by Roboflow Universe Projects; source project "
    "https://universe.roboflow.com/roboflow-universe-projects/hard-hats-fhbh5/dataset/2"
)
SOURCE_URL = (
    "https://huggingface.co/datasets/keremberke/hard-hat-detection/resolve/"
    f"{DATASET_REVISION}/data/test.zip"
)
EXPECTED_SIZE_BYTES = 114_425_180
EXPECTED_SHA256 = "e21ca22f4d69411af6e7c00b6d00ea30252867ac2d0f7cbef894b6ba9b9204c3"
EXPECTED_IMAGES = 2001
CATEGORY_MAP = {"hardhat": "Hardhat", "no-hardhat": "NO-Hardhat"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_archive(archive: Path) -> tuple[dict, dict]:
    if archive.stat().st_size != EXPECTED_SIZE_BYTES:
        raise ValueError(f"archive size mismatch: expected {EXPECTED_SIZE_BYTES} bytes")
    archive_hash = sha256_file(archive)
    if archive_hash != EXPECTED_SHA256:
        raise ValueError(f"archive SHA-256 mismatch: {archive_hash}")

    with ZipFile(archive) as zipped:
        names: set[str] = set()
        member_names: list[str] = []
        for info in zipped.infolist():
            name = info.filename.replace("\\", "/")
            path = PurePosixPath(name)
            mode = (info.external_attr >> 16) & 0xFFFF
            if path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]):
                raise ValueError(f"unsafe archive path: {info.filename}")
            if stat.S_ISLNK(mode) or mode & 0o111:
                raise ValueError(f"archive contains a link or executable entry: {info.filename}")
            if info.is_dir() or len(path.parts) != 1:
                raise ValueError(f"unexpected archive directory structure: {info.filename}")
            if path.suffix.casefold() not in {".jpg", ".json"}:
                raise ValueError(f"unexpected archive file extension: {info.filename}")
            if name.casefold() in names:
                raise ValueError(f"duplicate archive path: {info.filename}")
            names.add(name.casefold())
            member_names.append(name)
        if "_annotations.coco.json" not in names:
            raise ValueError("COCO annotation file is missing")
        image_names = sorted(name for name in member_names if name.casefold().endswith(".jpg"))
        if len(image_names) != EXPECTED_IMAGES:
            raise ValueError(f"expected {EXPECTED_IMAGES} JPG files, found {len(image_names)}")
        bad_member = zipped.testzip()
        if bad_member:
            raise ValueError(f"archive CRC check failed at {bad_member}")
        annotations = json.loads(zipped.read("_annotations.coco.json"))
        return annotations, {"sha256": archive_hash, "size_bytes": archive.stat().st_size,
                             "image_member_names": sorted(image_names)}


def _create_manifest(annotations: dict, archive_info: dict, image_dir: Path,
                     retrieved_utc: str) -> tuple[dict, dict]:
    images = annotations.get("images")
    labels = annotations.get("annotations")
    categories = annotations.get("categories")
    if not isinstance(images, list) or not isinstance(labels, list) or not isinstance(categories, list):
        raise ValueError("COCO annotations must contain image, annotation, and category arrays")
    catmap: dict[int, str] = {}
    for category in categories:
        name = category.get("name", "").casefold()
        if name not in CATEGORY_MAP or category.get("id") in catmap:
            raise ValueError(f"unexpected or duplicate COCO category: {category}")
        catmap[category["id"]] = CATEGORY_MAP[name]
    if set(catmap.values()) != set(CATEGORY_MAP.values()):
        raise ValueError("COCO categories do not map exactly to hardhat and no-hardhat")

    image_by_id: dict[int, dict] = {}
    file_names: set[str] = set()
    for image in images:
        image_id = image.get("id")
        filename = image.get("file_name")
        path = PurePosixPath(str(filename).replace("\\", "/"))
        if not isinstance(image_id, int) or image_id in image_by_id:
            raise ValueError(f"duplicate or invalid image ID: {image_id}")
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 1 or path.suffix.casefold() != ".jpg":
            raise ValueError(f"unexpected image filename: {filename}")
        if filename.casefold() in file_names:
            raise ValueError(f"duplicate image filename: {filename}")
        file_names.add(filename.casefold())
        if filename not in archive_info["image_member_names"]:
            raise ValueError(f"annotation refers to missing archive image: {filename}")
        width, height = image.get("width"), image.get("height")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise ValueError(f"invalid image dimensions for {filename}")
        image_by_id[image_id] = image
    if len(images) != EXPECTED_IMAGES or len(file_names) != EXPECTED_IMAGES:
        raise ValueError(f"expected {EXPECTED_IMAGES} uniquely named images")
    if {name.casefold() for name in archive_info["image_member_names"]} != file_names:
        raise ValueError("archive images and annotation image filenames do not match exactly")

    annotation_ids: set[int] = set()
    per_image: dict[int, list[dict]] = {image_id: [] for image_id in image_by_id}
    class_counts: Counter[str] = Counter()
    for annotation in labels:
        annotation_id = annotation.get("id")
        if not isinstance(annotation_id, int) or annotation_id in annotation_ids:
            raise ValueError(f"duplicate or invalid annotation ID: {annotation_id}")
        annotation_ids.add(annotation_id)
        image_id = annotation.get("image_id")
        if image_id not in image_by_id:
            raise ValueError(f"annotation {annotation_id} refers to unknown image {image_id}")
        category_id = annotation.get("category_id")
        if category_id not in catmap:
            raise ValueError(f"annotation {annotation_id} refers to unknown category {category_id}")
        box = annotation.get("bbox")
        try:
            x, y, width, height = (float(value) for value in box)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"annotation {annotation_id} has malformed bbox") from exc
        image = image_by_id[image_id]
        if (not all(math.isfinite(value) for value in (x, y, width, height)) or
                x < 0 or y < 0 or width <= 0 or height <= 0 or
                x + width > image["width"] + 1e-6 or y + height > image["height"] + 1e-6):
            raise ValueError(f"annotation {annotation_id} has invalid/out-of-bounds bbox {box}")
        class_name = catmap[category_id]
        class_counts[class_name] += 1
        per_image[image_id].append({
            "source_annotation_id": annotation_id,
            "class_name": class_name,
            "bbox_xyxy": [x, y, x + width, y + height],
        })

    manifest_images = []
    bad_image_dimensions = []
    for image in sorted(images, key=lambda item: item["id"]):
        filename = image["file_name"]
        actual = cv2.imread(str(image_dir / filename)) if (image_dir / filename).is_file() else None
        # Before extraction, dimensions are checked against image headers after safe extraction.
        if actual is not None and (actual.shape[1] != image["width"] or actual.shape[0] != image["height"]):
            bad_image_dimensions.append(filename)
        manifest_images.append({
            "image_path": f"images/{filename}",
            "image_id": image["id"],
            "ground_truth": [{"class_name": item["class_name"], "bbox_xyxy": item["bbox_xyxy"]}
                             for item in per_image[image["id"]]],
        })
    if bad_image_dimensions:
        raise ValueError(f"decoded image dimensions differ from COCO metadata: {bad_image_dimensions[:10]}")

    validation = {
        "image_count": len(images),
        "archive_image_count": len(archive_info["image_member_names"]),
        "annotation_count": len(labels),
        "unique_image_id_count": len(image_by_id),
        "unique_annotation_id_count": len(annotation_ids),
        "annotation_class_counts": dict(class_counts),
        "images_without_annotations": sum(not per_image[image["id"]] for image in images),
        "missing_images": [],
        "missing_annotations": [],
        "invalid_annotations": 0,
        "duplicate_image_ids": 0,
        "duplicate_annotation_ids": 0,
        "dimension_mismatches": bad_image_dimensions,
        "mapping": "COCO category 0 hardhat -> Hardhat; category 1 no-hardhat -> NO-Hardhat; xywh -> xyxy",
    }
    manifest = {
        "dataset": DATASET_NAME,
        "dataset_revision": DATASET_REVISION,
        "dataset_license": DATASET_LICENSE,
        "attribution": ATTRIBUTION,
        "source_url": SOURCE_URL,
        "archive_sha256": archive_info["sha256"],
        "archive_size_bytes": archive_info["size_bytes"],
        "retrieved_utc": retrieved_utc,
        "classes": ["Hardhat", "NO-Hardhat"],
        "validation": validation,
        "images": manifest_images,
    }
    return manifest, validation


def prepare(archive: Path, destination: Path, retrieved_utc: str) -> dict:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing evaluation directory: {destination}")
    annotations, archive_info = _validate_archive(archive)
    images_dir = destination / "images"
    images_dir.mkdir(parents=True, exist_ok=False)
    try:
        with ZipFile(archive) as zipped:
            for filename in archive_info["image_member_names"]:
                with zipped.open(filename) as source, (images_dir / filename).open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
            with zipped.open("_annotations.coco.json") as source, (destination / "annotations.coco.json").open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
        manifest, validation = _create_manifest(annotations, archive_info, images_dir, retrieved_utc)
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (destination / "validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
        return validation
    except Exception:
        # Leave partial output visible for inspection; never delete user data implicitly.
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--retrieved-utc", required=True)
    args = parser.parse_args()
    result = prepare(args.archive, args.destination, args.retrieved_utc)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
