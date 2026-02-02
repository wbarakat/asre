"""Tests for AuthStatusMapper — maps auth status codes to canonical values and event types."""

from __future__ import annotations

from asre.config.source_schema import AuthStatusMap
from asre.canonicalize.auth_status_mapper import AuthStatusMapper
from asre.models.canonical_event import CanonicalEvent

from datetime import datetime, timezone


def _make_auth_status_map() -> AuthStatusMap:
    """Create a standard auth_status_map config matching auth_portal.yaml."""
    return AuthStatusMap(
        source_field="auth_status_code",
        mappings={
            "A": "approved",
            "D": "denied",
            "P": "pending",
            "M": "modified",
        },
    )


def _make_event(
    auth_status: str | None = None,
    auth_flag: bool | None = None,
    event_type: str = "UNKNOWN",
) -> CanonicalEvent:
    """Create a minimal CanonicalEvent for testing."""
    return CanonicalEvent(
        event_id="evt-001",
        patient_key="PAT-001",
        event_type=event_type,
        event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        source_system="auth_portal",
        source_record_id="AUTH-001",
        facility_raw="General Hospital",
        ingested_at=datetime.now(timezone.utc),
        batch_id="batch-001",
        auth_status=auth_status,
        auth_flag=auth_flag,
    )


class TestAuthStatusMapperConstruction:
    def test_takes_auth_status_map_config(self) -> None:
        config = _make_auth_status_map()
        mapper = AuthStatusMapper(config)
        assert mapper.auth_status_map is config


class TestAuthStatusMapping:
    def test_approved_status(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "A"}
        result = mapper.apply(event, raw_record)
        assert result.auth_status == "approved"

    def test_denied_status(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "D"}
        result = mapper.apply(event, raw_record)
        assert result.auth_status == "denied"

    def test_pending_status(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "P"}
        result = mapper.apply(event, raw_record)
        assert result.auth_status == "pending"

    def test_modified_status(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "M"}
        result = mapper.apply(event, raw_record)
        assert result.auth_status == "modified"

    def test_unknown_status_code_returns_none(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "X"}
        result = mapper.apply(event, raw_record)
        assert result.auth_status is None

    def test_missing_source_field_returns_none(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"other_field": "value"}
        result = mapper.apply(event, raw_record)
        assert result.auth_status is None

    def test_none_source_value_returns_none(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": None}
        result = mapper.apply(event, raw_record)
        assert result.auth_status is None


class TestEventTypeDerivation:
    def test_approved_derives_auth_approved(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "A"}
        result = mapper.apply(event, raw_record)
        assert result.event_type == "AUTH_APPROVED"

    def test_denied_derives_auth_denied(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "D"}
        result = mapper.apply(event, raw_record)
        assert result.event_type == "AUTH_DENIED"

    def test_pending_derives_auth_requested(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "P"}
        result = mapper.apply(event, raw_record)
        assert result.event_type == "AUTH_REQUESTED"

    def test_modified_keeps_event_type_from_event_type_rules(self) -> None:
        """Modified status doesn't have a specific event_type derivation.
        The event_type should come from event_type_rules, not auth_status_map."""
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event(event_type="AUTH_MODIFIED")
        raw_record = {"auth_status_code": "M"}
        result = mapper.apply(event, raw_record)
        # Modified doesn't override event_type — keeps whatever was already set
        assert result.event_type == "AUTH_MODIFIED"

    def test_unknown_status_does_not_override_event_type(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event(event_type="AUTH_REQUESTED")
        raw_record = {"auth_status_code": "X"}
        result = mapper.apply(event, raw_record)
        assert result.event_type == "AUTH_REQUESTED"


class TestAuthFlag:
    def test_auth_flag_set_true_on_approved(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "A"}
        result = mapper.apply(event, raw_record)
        assert result.auth_flag is True

    def test_auth_flag_set_true_on_denied(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "D"}
        result = mapper.apply(event, raw_record)
        assert result.auth_flag is True

    def test_auth_flag_set_true_on_pending(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "P"}
        result = mapper.apply(event, raw_record)
        assert result.auth_flag is True

    def test_auth_flag_set_true_on_modified(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "M"}
        result = mapper.apply(event, raw_record)
        assert result.auth_flag is True

    def test_auth_flag_set_true_even_on_unknown_code(self) -> None:
        """auth_flag is True for ALL auth source events, regardless of status mapping."""
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "X"}
        result = mapper.apply(event, raw_record)
        assert result.auth_flag is True

    def test_auth_flag_true_even_when_source_field_missing(self) -> None:
        """auth_flag should be True for all auth events regardless."""
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"other": "val"}
        result = mapper.apply(event, raw_record)
        assert result.auth_flag is True


class TestMutatesEventInPlace:
    def test_returns_same_event_object(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "A"}
        result = mapper.apply(event, raw_record)
        assert result is event

    def test_preserves_existing_event_fields(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": "A"}
        result = mapper.apply(event, raw_record)
        assert result.patient_key == "PAT-001"
        assert result.source_system == "auth_portal"
        assert result.facility_raw == "General Hospital"


class TestWhitespaceHandling:
    def test_strips_whitespace_from_status_code(self) -> None:
        mapper = AuthStatusMapper(_make_auth_status_map())
        event = _make_event()
        raw_record = {"auth_status_code": " A "}
        result = mapper.apply(event, raw_record)
        assert result.auth_status == "approved"
        assert result.event_type == "AUTH_APPROVED"
