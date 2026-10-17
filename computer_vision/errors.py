class VisionError(RuntimeError):
    """Base class for vision pipeline errors safe to display to a local operator."""


class ModelLoadError(VisionError):
    """YOLO implementation or weights could not be loaded."""


class InferenceError(VisionError):
    """The selected detector failed while processing a frame."""


class UnsupportedClassError(VisionError):
    """Requested classes are not present in the selected model metadata."""


class InvalidImageError(VisionError):
    """An image could not be decoded."""


class VideoSourceError(VisionError):
    """A file, webcam or RTSP source could not be opened/read."""
