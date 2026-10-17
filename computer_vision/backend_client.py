import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from contracts.v1 import SafetyEvent
from pydantic import ValidationError


class BackendDeliveryError(RuntimeError):
    """The event was not accepted by the configured backend."""


class BackendEventClient:
    """Small HTTP client; callers can retry the same event ID safely."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 5.0,
        max_attempts: int = 3,
        bearer_token: str | None = None,
    ) -> None:
        self.endpoint = base_url.rstrip("/") + "/api/v1/events"
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.bearer_token = bearer_token if bearer_token is not None else os.environ.get("HELMET_API_TOKEN")

    def send(self, event: SafetyEvent) -> SafetyEvent:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        request = Request(
            self.endpoint,
            data=event.model_dump_json().encode("utf-8"),
            headers=headers,
            method="POST",
        )
        for attempt in range(self.max_attempts):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    if response.status not in (200, 201):
                        raise BackendDeliveryError(
                            f"backend returned unexpected HTTP {response.status}"
                        )
                    try:
                        body = json.loads(response.read().decode("utf-8"))
                        return SafetyEvent.model_validate(body)
                    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
                        raise BackendDeliveryError("backend returned an invalid SafetyEvent response") from exc
            except HTTPError as exc:
                if exc.code == 409:
                    # Event IDs are idempotency keys. A prior successful delivery is done.
                    return event
                if exc.code < 500 and exc.code != 429:
                    raise BackendDeliveryError(f"backend rejected event with HTTP {exc.code}") from exc
                if attempt + 1 == self.max_attempts:
                    raise BackendDeliveryError(
                        f"backend remained unavailable after {self.max_attempts} attempts"
                    ) from exc
            except (URLError, TimeoutError) as exc:
                if attempt + 1 == self.max_attempts:
                    raise BackendDeliveryError(
                        f"backend was unreachable after {self.max_attempts} attempts"
                    ) from exc
            if attempt + 1 < self.max_attempts:
                time.sleep(0.1 * (2**attempt))
        raise BackendDeliveryError("backend did not accept the safety event")
