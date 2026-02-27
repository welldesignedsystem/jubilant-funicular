"""
models.py

Domain models for the Shipyard Hull Fabrication & Assembly
Project Management System.

Entities
--------
- Project
- Phase
- Stage
- StageDependency
- StageStatusUpdate
- Stakeholder
- ProjectStakeholder
- Baseline
- BaselineStageSnapshot
- ChangeRequest
- AuditTrailEntry
- NotificationLog

All models use Python dataclasses for clean, framework-agnostic definitions.
UUID primary keys are used throughout for portability.
Timestamps are always stored in UTC.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class StageStatus(str, Enum):
    """Lifecycle status of an individual project stage."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class ChangeRequestStatus(str, Enum):
    """Approval workflow status of a baseline change request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ChangeType(str, Enum):
    """
    Classification of a baseline change request.

    INITIAL_BASELINE  – First approved baseline set at project kickoff.
    DELAY             – Schedule slip due to external factors (e.g. supplier delay).
    SCOPE_CHANGE      – Modification to the agreed project scope; requires
                        Owner Representative sign-off in addition to standard approval.
    COST_CHANGE       – Adjustment driven by budget or resource changes.
    OTHER             – Any change not covered by the above categories.
    """
    INITIAL_BASELINE = "initial_baseline"
    DELAY = "delay"
    SCOPE_CHANGE = "scope_change"
    COST_CHANGE = "cost_change"
    OTHER = "other"


class NotificationType(str, Enum):
    """Category of a stakeholder notification event."""
    BASELINE_SET = "baseline_set"
    BASELINE_RESET = "baseline_reset"
    BASELINE_CHANGE = "baseline_change"
    DELAY_NOTIFICATION = "delay_notification"
    STAGE_BLOCKED = "stage_blocked"
    CHANGE_REQUEST_SUBMITTED = "change_request_submitted"
    CHANGE_REQUEST_APPROVED = "change_request_approved"
    CHANGE_REQUEST_REJECTED = "change_request_rejected"


class StakeholderRole(str, Enum):
    """
    Standard roles within the project management system.
    Additional roles may be defined at the project level.
    """
    LEAD_PROJECT_MANAGER = "lead_project_manager"
    BASELINE_APPROVER = "baseline_approver"
    OWNER_REPRESENTATIVE = "owner_representative"
    PROCUREMENT_LEAD = "procurement_lead"
    QA_CLASSIFICATION_OFFICER = "qa_classification_officer"
    TEAM_MEMBER = "team_member"


class DeviationStatus(str, Enum):
    """Deviation of a stage's current planned end vs. its baseline end date."""
    ON_BASELINE = "on_baseline"
    AHEAD = "ahead"       # Current planned end is earlier than baseline end
    DELAYED = "delayed"   # Current planned end is later than baseline end


# ---------------------------------------------------------------------------
# Core Project Entities
# ---------------------------------------------------------------------------


@dataclass
class Project:
    """
    Top-level container for a hull fabrication and assembly project.

    A project owns a configurable set of phases (which in turn own stages),
    a series of baselines, and all associated change requests and audit records.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = ""
    description: str = ""
    shipyard_name: str = ""
    vessel_type: str = ""

    # Schedule
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None

    # Computed / updated summary fields
    overall_progress_pct: float = 0.0          # 0.0 – 100.0
    total_planned_duration_days: int = 0
    total_actual_duration_days: int = 0
    total_baseline_duration_days: int = 0

    # Active baseline reference (FK to Baseline.id); None until first baseline is set
    active_baseline_id: Optional[uuid.UUID] = None

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by_id: Optional[uuid.UUID] = None   # FK → Stakeholder.id


@dataclass
class Phase:
    """
    A named grouping of related stages within a project.

    Phases are fully configurable: they may be added, removed, or reordered
    by authorized users at any point without system-level changes.
    The `order` field controls display sequence in the Gantt chart.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    project_id: uuid.UUID = field(default_factory=uuid.uuid4)   # FK → Project.id
    name: str = ""
    description: str = ""
    order: int = 0          # 1-based display order within the project

    # Computed from child stages
    overall_progress_pct: float = 0.0
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Stage:
    """
    An individual unit of work within a phase.

    Each stage tracks its own planned, actual, and baseline schedule independently.
    Baseline dates are written once (at baseline approval) and are thereafter
    read-only; they may only be updated through an approved ChangeRequest.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    phase_id: uuid.UUID = field(default_factory=uuid.uuid4)     # FK → Phase.id
    project_id: uuid.UUID = field(default_factory=uuid.uuid4)   # FK → Project.id (denormalised for query convenience)
    name: str = ""
    description: str = ""
    order: int = 0          # Display order within the phase

    # Planned schedule (mutable; drives current Gantt view)
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    planned_duration_days: Optional[int] = None

    # Actuals (entered progressively as work is completed)
    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None          # Cannot be set without actual_start_date
    actual_duration_days: Optional[int] = None

    # Baseline (locked at time of most-recent approved baseline; read-only thereafter)
    baseline_start_date: Optional[date] = None
    baseline_end_date: Optional[date] = None
    baseline_duration_days: Optional[int] = None

    # Progress & status
    status: StageStatus = StageStatus.NOT_STARTED
    progress_pct: float = 0.0       # 0.0 – 100.0
    comments: str = ""

    # Deviation (computed; not stored as source-of-truth)
    deviation_days: Optional[int] = None            # positive = delayed, negative = ahead
    deviation_status: Optional[DeviationStatus] = None

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by_id: Optional[uuid.UUID] = None       # FK → Stakeholder.id


@dataclass
class StageDependency:
    """
    Records a predecessor → successor dependency between two stages.

    Both stages must belong to the same project.
    Dependency type is currently fixed as Finish-to-Start (the only type
    supported in this iteration), but the field is included for future extension.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    project_id: uuid.UUID = field(default_factory=uuid.uuid4)
    predecessor_stage_id: uuid.UUID = field(default_factory=uuid.uuid4)   # FK → Stage.id
    successor_stage_id: uuid.UUID = field(default_factory=uuid.uuid4)     # FK → Stage.id
    dependency_type: str = "finish_to_start"    # Reserved for future FS/SS/FF/SF support
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class StageStatusUpdate:
    """
    Immutable log of every status/progress update applied to a stage.

    Provides a full history of how a stage progressed over time and who
    made each change, satisfying the auditability non-functional requirement.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    stage_id: uuid.UUID = field(default_factory=uuid.uuid4)         # FK → Stage.id
    project_id: uuid.UUID = field(default_factory=uuid.uuid4)
    updated_by_id: uuid.UUID = field(default_factory=uuid.uuid4)    # FK → Stakeholder.id

    previous_status: Optional[StageStatus] = None
    new_status: StageStatus = StageStatus.NOT_STARTED
    previous_progress_pct: Optional[float] = None
    new_progress_pct: float = 0.0

    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    comments: str = ""

    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Stakeholder Entities
# ---------------------------------------------------------------------------


@dataclass
class Stakeholder:
    """
    A person who participates in or is notified about the project.

    Stakeholders are global to the system; their role within a specific
    project is defined by the ProjectStakeholder join entity.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    full_name: str = ""
    email: str = ""
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ProjectStakeholder:
    """
    Associates a Stakeholder with a Project and assigns them a role.

    A stakeholder may hold different roles on different projects.
    Multiple stakeholders may share the same role on a project.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    project_id: uuid.UUID = field(default_factory=uuid.uuid4)      # FK → Project.id
    stakeholder_id: uuid.UUID = field(default_factory=uuid.uuid4)  # FK → Stakeholder.id
    role: StakeholderRole = StakeholderRole.TEAM_MEMBER
    assigned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Baseline Entities
# ---------------------------------------------------------------------------


@dataclass
class Baseline:
    """
    A versioned, approved snapshot of a project's planned schedule.

    Once set, a baseline's stage snapshots are immutable. Any subsequent
    schedule change must be routed through an approved ChangeRequest,
    which then creates a new Baseline version.

    `is_active` — only one baseline per project may be active at a time.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    project_id: uuid.UUID = field(default_factory=uuid.uuid4)  # FK → Project.id
    version_number: int = 1                                     # Increments with each new baseline
    set_by_id: uuid.UUID = field(default_factory=uuid.uuid4)   # FK → Stakeholder.id
    set_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    notes: str = ""

    # Linked change request that authorised this baseline (None for initial baseline)
    change_request_id: Optional[uuid.UUID] = None               # FK → ChangeRequest.id


@dataclass
class BaselineStageSnapshot:
    """
    Captures the planned dates for a single stage at the time a baseline was set.

    These records are write-once and must never be modified after creation.
    They are the authoritative source for deviation calculations.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    baseline_id: uuid.UUID = field(default_factory=uuid.uuid4)  # FK → Baseline.id
    stage_id: uuid.UUID = field(default_factory=uuid.uuid4)     # FK → Stage.id
    project_id: uuid.UUID = field(default_factory=uuid.uuid4)

    baseline_start_date: Optional[date] = None
    baseline_end_date: Optional[date] = None
    baseline_duration_days: Optional[int] = None

    snapshotted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Change Control Entities
# ---------------------------------------------------------------------------


@dataclass
class ChangeRequest:
    """
    A formal request to modify the approved project baseline.

    No baseline change may take effect until a ChangeRequest reaches
    APPROVED status. SCOPE_CHANGE types additionally require the
    Owner Representative to be recorded as the approver (enforced
    at the service layer).

    `schedule_impact_days` — positive = delay, negative = schedule reduction.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    project_id: uuid.UUID = field(default_factory=uuid.uuid4)      # FK → Project.id
    requested_by_id: uuid.UUID = field(default_factory=uuid.uuid4) # FK → Stakeholder.id
    approver_id: Optional[uuid.UUID] = None                        # FK → Stakeholder.id

    change_type: ChangeType = ChangeType.OTHER
    reason: str = ""
    schedule_impact_days: int = 0   # Positive = delay; negative = reduction
    cost_impact: Optional[float] = None
    status: ChangeRequestStatus = ChangeRequestStatus.PENDING

    # Approval / rejection
    reviewed_at: Optional[datetime] = None
    reviewer_comments: str = ""

    # Stakeholder comments captured at submission
    stakeholder_comments: str = ""

    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Audit & Notification Entities
# ---------------------------------------------------------------------------


@dataclass
class AuditTrailEntry:
    """
    Immutable record of every approved baseline change.

    Entries are written by the system automatically when a ChangeRequest
    is approved and a new Baseline is created. They must never be edited
    or deleted, satisfying the immutable audit trail requirement.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    project_id: uuid.UUID = field(default_factory=uuid.uuid4)
    sequence_number: int = 0                                        # Monotonically increasing per project

    baseline_id: uuid.UUID = field(default_factory=uuid.uuid4)     # FK → Baseline.id (resulting baseline)
    change_request_id: Optional[uuid.UUID] = None                  # FK → ChangeRequest.id

    changed_by_id: uuid.UUID = field(default_factory=uuid.uuid4)   # FK → Stakeholder.id
    approved_by_id: Optional[uuid.UUID] = None                     # FK → Stakeholder.id

    change_type: ChangeType = ChangeType.OTHER
    reason: str = ""
    schedule_impact_days: int = 0
    stakeholder_comments: str = ""
    reviewer_comments: str = ""

    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class NotificationLog:
    """
    Structured record of every stakeholder notification dispatched by the system.

    Entries are generated automatically on baseline changes, stage blocks,
    delay flags, and change request state transitions. The log is auditable
    and read-only once written.
    """
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    project_id: uuid.UUID = field(default_factory=uuid.uuid4)
    stakeholder_id: uuid.UUID = field(default_factory=uuid.uuid4)  # FK → Stakeholder.id

    notification_type: NotificationType = NotificationType.BASELINE_CHANGE
    role_at_time_of_notification: StakeholderRole = StakeholderRole.TEAM_MEMBER

    # Optional references to the triggering entities
    change_request_id: Optional[uuid.UUID] = None   # FK → ChangeRequest.id
    baseline_id: Optional[uuid.UUID] = None         # FK → Baseline.id
    stage_id: Optional[uuid.UUID] = None            # FK → Stage.id

    comments: str = ""
    notified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))