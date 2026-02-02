"""Auth status mapper — maps auth status codes to canonical values and event types."""

from __future__ import annotations

from typing import Any

from asre.config.source_schema import AuthStatusMap
from asre.models.canonical_event import CanonicalEvent


# Mapping from canonical auth status to canonical event type
_STATUS_TO_EVENT_TYPE: dict[str, str] = {
    "approved": "AUTH_APPROVED",
    "denied": "AUTH_DENIED",
    "pending": "AUTH_REQUESTED",
}


class AuthStatusMapper:
    """Maps source auth status codes to standardized canonical values.

    Responsibilities:
    - Maps source status code to canonical auth_status (approved, denied, pending, modified)
    - Derives event_type from mapped status when applicable
    - Sets auth_flag=True on all auth events
    """

    def __init__(self, auth_status_map: AuthStatusMap) -> None:
        self.auth_status_map = auth_status_map

    def apply(self, event: CanonicalEvent, raw_record: dict[str, Any]) -> CanonicalEvent:
        """Apply auth status mapping to a CanonicalEvent.

        Args:
            event: CanonicalEvent to update (mutated in place).
            raw_record: Raw record dict containing source auth status field.

        Returns:
            The same CanonicalEvent with auth_status, event_type, auth_flag set.
        """
        # Always set auth_flag for auth source events
        event.auth_flag = True

        # Look up source status code
        source_value = raw_record.get(self.auth_status_map.source_field)
        if source_value is None:
            return event

        status_code = str(source_value).strip()
        canonical_status = self.auth_status_map.mappings.get(status_code)

        if canonical_status is not None:
            event.auth_status = canonical_status

            # Derive event_type from canonical status if mapping exists
            derived_event_type = _STATUS_TO_EVENT_TYPE.get(canonical_status)
            if derived_event_type is not None:
                event.event_type = derived_event_type

        return event
