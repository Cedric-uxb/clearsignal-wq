from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum


def _require_non_empty_string(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_tuple(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    return value


def _require_tuple_items(
    value: object, field_name: str, item_type: type[object]
) -> tuple[object, ...]:
    items = _require_tuple(value, field_name)
    if not all(isinstance(item, item_type) for item in items):
        raise TypeError(f"{field_name} contains an invalid item type")
    return items


def _require_sensor_tuple(value: object) -> tuple[object, ...]:
    sensors = _require_tuple_items(value, "affected_sensors", str)
    if not sensors or any(not sensor.strip() for sensor in sensors):
        raise ValueError("affected_sensors must contain non-empty sensor names")
    return sensors


def _require_enum(value: object, field_name: str, enum_type: type[Enum]) -> None:
    if not isinstance(value, enum_type):
        raise TypeError(f"{field_name} must be a {enum_type.__name__}")


def _require_exact_type(
    value: object, field_name: str, expected_type: type[object]
) -> None:
    if type(value) is not expected_type:
        raise TypeError(f"{field_name} must be a {expected_type.__name__}")


def _require_utc_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must have a UTC offset of 0")


class TriageStatus(str, Enum):
    POSSIBLE_WATER_QUALITY_EVENT = "possible_water_quality_event"
    SENSOR_FAULT_OR_DRIFT = "sensor_fault_or_drift"
    DATA_INTEGRITY_ISSUE = "data_integrity_issue"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceStrength(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DataProvenance(str, Enum):
    PUBLIC_REAL_DATA = "public_real_data"
    SYNTHETIC_SCENARIO = "synthetic_scenario"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    code: str
    message: str
    sensor: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.code, "code")
        _require_non_empty_string(self.message, "message")
        if self.sensor is not None:
            _require_non_empty_string(self.sensor, "sensor")


@dataclass(frozen=True, slots=True)
class PointFlag:
    timestamp: datetime
    sensor: str
    code: str
    severity: EvidenceStrength
    details: tuple[EvidenceItem, ...] = ()

    def __post_init__(self) -> None:
        _require_utc_datetime(self.timestamp, "timestamp")
        _require_non_empty_string(self.sensor, "sensor")
        _require_non_empty_string(self.code, "code")
        _require_enum(self.severity, "severity", EvidenceStrength)
        _require_tuple_items(self.details, "details", EvidenceItem)


@dataclass(frozen=True, slots=True)
class DetectionEvent:
    event_id: str
    start_at: datetime
    end_at: datetime
    affected_sensors: tuple[str, ...]
    flags: tuple[PointFlag, ...]
    source_label: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.event_id, "event_id")
        _require_utc_datetime(self.start_at, "start_at")
        _require_utc_datetime(self.end_at, "end_at")
        if self.source_label is not None:
            _require_non_empty_string(self.source_label, "source_label")
        if self.start_at > self.end_at:
            raise ValueError("start_at must not be later than end_at")
        _require_sensor_tuple(self.affected_sensors)
        _require_tuple_items(self.flags, "flags", PointFlag)


@dataclass(frozen=True, slots=True)
class EventAssessment:
    reliability: tuple[tuple[str, float], ...]
    corroborating_sensor_count: int
    has_data_integrity_evidence: bool
    evidence: tuple[EvidenceItem, ...]

    def __post_init__(self) -> None:
        _require_exact_type(
            self.corroborating_sensor_count, "corroborating_sensor_count", int
        )
        _require_exact_type(
            self.has_data_integrity_evidence, "has_data_integrity_evidence", bool
        )
        reliability = _require_tuple(self.reliability, "reliability")
        for item in reliability:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], float)
            ):
                raise TypeError("reliability contains an invalid item type")
            _require_non_empty_string(item[0], "reliability")
        _require_tuple_items(self.evidence, "evidence", EvidenceItem)


@dataclass(frozen=True, slots=True)
class TriageEvent:
    event_id: str
    start_at: datetime
    end_at: datetime
    triage_status: TriageStatus
    evidence_strength: EvidenceStrength
    affected_sensors: tuple[str, ...]
    evidence: tuple[EvidenceItem, ...]
    recommended_action: str
    data_provenance: DataProvenance
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string(self.event_id, "event_id")
        _require_utc_datetime(self.start_at, "start_at")
        _require_utc_datetime(self.end_at, "end_at")
        if self.start_at > self.end_at:
            raise ValueError("start_at must not be later than end_at")
        _require_enum(self.triage_status, "triage_status", TriageStatus)
        _require_enum(
            self.evidence_strength, "evidence_strength", EvidenceStrength
        )
        sensors = _require_sensor_tuple(self.affected_sensors)
        if len(set(sensors)) != len(sensors):
            raise ValueError("affected_sensors must not contain duplicates")
        evidence = _require_tuple_items(self.evidence, "evidence", EvidenceItem)
        if not evidence:
            raise ValueError("evidence must not be empty")
        _require_non_empty_string(self.recommended_action, "recommended_action")
        _require_enum(self.data_provenance, "data_provenance", DataProvenance)
        limitations = _require_tuple_items(self.limitations, "limitations", str)
        if not limitations:
            raise ValueError("limitations must not be empty")
        for limitation in limitations:
            _require_non_empty_string(limitation, "limitations")


@dataclass(frozen=True, slots=True)
class EventMetrics:
    recall: float
    precision: float
    invalid_alerts_per_day: float
    detection_delay_minutes: float
    matched_events: int
    predicted_events: int
    labelled_events: int

    def __post_init__(self) -> None:
        _require_exact_type(self.recall, "recall", float)
        _require_exact_type(self.precision, "precision", float)
        _require_exact_type(
            self.invalid_alerts_per_day, "invalid_alerts_per_day", float
        )
        _require_exact_type(
            self.detection_delay_minutes, "detection_delay_minutes", float
        )
        _require_exact_type(self.matched_events, "matched_events", int)
        _require_exact_type(self.predicted_events, "predicted_events", int)
        _require_exact_type(self.labelled_events, "labelled_events", int)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    data_hash: str
    config_version: str
    model_version: str
    provenance: DataProvenance
    events: tuple[TriageEvent, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_string(self.data_hash, "data_hash")
        _require_non_empty_string(self.config_version, "config_version")
        _require_non_empty_string(self.model_version, "model_version")
        _require_enum(self.provenance, "provenance", DataProvenance)
        events = _require_tuple_items(self.events, "events", TriageEvent)
        warnings = _require_tuple_items(self.warnings, "warnings", str)
        for warning in warnings:
            _require_non_empty_string(warning, "warnings")
        if any(event.data_provenance is not self.provenance for event in events):
            raise ValueError("events must have the same provenance as PipelineResult")


def _to_serializable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _to_serializable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_to_serializable(item) for item in value]
    return value


def contract_to_dict(contract: object) -> dict[str, object]:
    if not is_dataclass(contract) or isinstance(contract, type):
        raise TypeError("contract must be a dataclass instance")
    return {
        field.name: _to_serializable(getattr(contract, field.name))
        for field in fields(contract)
    }
