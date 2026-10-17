class StorageError(RuntimeError):
    """Persistence failure without leaking local database details to clients."""


class DuplicateEventError(RuntimeError):
    """A telemetry event ID was already accepted."""


class IncidentTransitionError(RuntimeError):
    """Requested incident state transition is not allowed."""
