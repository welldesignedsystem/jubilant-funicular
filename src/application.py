"""
application.py

Application layer for the Shipyard Hull Fabrication & Assembly
Project Management System.

Overview
--------
The application layer sits between the presentation layer (API / UI) and the
domain / service layer.  It is responsible for:

  1. Defining clean input/output DTOs (dataclasses) that carry only the data
     the presentation layer needs — no raw domain objects are leaked upward.
  2. Declaring abstract Repository interfaces so that the application layer
     remains fully persistence-agnostic (implementations live in infrastructure/).
  3. Declaring the UnitOfWork abstraction so that multiple repository mutations
     inside a single use case are wrapped in one atomic transaction.
  4. Implementing Use Case handlers — one class per user-facing operation —
     that orchestrate service calls, repository reads/writes, and side-effects
     (notifications, audit entries) in the correct order.

Structure
---------
DTOs
    ProjectDTO, PhaseDTO, StageDTO, StageDeviationDTO
    BaselineDTO, BaselineSnapshotDTO, BaselineReportDTO
    ChangeRequestDTO, AuditEntryDTO, NotificationLogDTO
    StakeholderDTO, ProjectStakeholderDTO

Repository interfaces
    AbstractProjectRepository
    AbstractPhaseRepository
    AbstractStageRepository
    AbstractStageDependencyRepository
    AbstractStageStatusUpdateRepository
    AbstractStakeholderRepository
    AbstractProjectStakeholderRepository
    AbstractBaselineRepository
    AbstractBaselineStageSnapshotRepository
    AbstractChangeRequestRepository
    AbstractAuditTrailRepository
    AbstractNotificationLogRepository

Unit of Work
    AbstractUnitOfWork

Use Cases
    --- Project management ---
    CreateProjectUseCase
    UpdateProjectUseCase
    GetProjectUseCase
    ListProjectsUseCase

    --- Phase management ---
    AddPhaseUseCase
    ReorderPhasesUseCase
    RemovePhaseUseCase

    --- Stage management ---
    AddStageUseCase
    UpdateStageScheduleUseCase
    UpdateStageProgressUseCase
    GetGanttDataUseCase

    --- Dependency management ---
    AddStageDependencyUseCase
    RemoveStageDependencyUseCase

    --- Baseline management ---
    SetInitialBaselineUseCase
    ResetBaselineUseCase
    GetBaselineHistoryUseCase
    GetBaselineReportUseCase

    --- Change control ---
    SubmitChangeRequestUseCase
    ApproveChangeRequestUseCase
    RejectChangeRequestUseCase
    ListChangeRequestsUseCase

    --- Audit & notifications ---
    GetAuditTrailUseCase
    ExportAuditTrailUseCase
    GetNotificationLogUseCase

    --- Stakeholder management ---
    CreateStakeholderUseCase
    AssignStakeholderUseCase
    RemoveStakeholderUseCase

Design notes
------------
- Use cases receive and return DTOs only; no domain objects cross the
  application boundary.
- Each use case accepts a UnitOfWork as its sole dependency.  The UoW
  exposes all repositories and handles commit/rollback.
- All timestamps flowing out are ISO-8601 strings (UTC) for easy JSON
  serialisation.
- Errors bubble up as ApplicationError (business) or ValueError (validation).
- Type annotations use standard library only (no third-party deps).
"""

from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from model import (
    AuditTrailEntry,
    Baseline,
    BaselineStageSnapshot,
    ChangeRequest,
    ChangeRequestStatus,
    ChangeType,
    DeviationStatus,
    NotificationLog,
    NotificationType,
    Phase,
    Project,
    ProjectStakeholder,
    Stage,
    StageDependency,
    StageStatus,
    StageStatusUpdate,
    Stakeholder,
    StakeholderRole,
)
from service import (
    AuditService,
    BaselineService,
    ChangeControlService,
    DependencyService,
    NotificationService,
    PhaseService,
    ProjectService,
    StageService,
    StakeholderService,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ApplicationError(Exception):
    """Raised when a use case cannot complete due to a business rule violation."""


class NotFoundError(ApplicationError):
    """Raised when a requested entity does not exist."""


class AuthorizationError(ApplicationError):
    """Raised when the acting user lacks the required role."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(dt: Optional[datetime]) -> Optional[str]:
    """Convert a datetime to an ISO-8601 UTC string, or None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _fmt_date(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


# ===========================================================================
# DTO DEFINITIONS
# ===========================================================================

# ---------------------------------------------------------------------------
# Stakeholder DTOs
# ---------------------------------------------------------------------------

@dataclass
class StakeholderDTO:
    id: str
    full_name: str
    email: str
    is_active: bool


@dataclass
class ProjectStakeholderDTO:
    id: str
    project_id: str
    stakeholder_id: str
    full_name: str
    email: str
    role: str
    assigned_at: str


# ---------------------------------------------------------------------------
# Project DTOs
# ---------------------------------------------------------------------------

@dataclass
class ProjectDTO:
    id: str
    name: str
    description: str
    shipyard_name: str
    vessel_type: str
    planned_start_date: Optional[str]
    planned_end_date: Optional[str]
    actual_start_date: Optional[str]
    actual_end_date: Optional[str]
    overall_progress_pct: float
    total_planned_duration_days: int
    total_actual_duration_days: int
    total_baseline_duration_days: int
    active_baseline_id: Optional[str]
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Phase DTOs
# ---------------------------------------------------------------------------

@dataclass
class PhaseDTO:
    id: str
    project_id: str
    name: str
    description: str
    order: int
    overall_progress_pct: float
    planned_start_date: Optional[str]
    planned_end_date: Optional[str]
    actual_start_date: Optional[str]
    actual_end_date: Optional[str]
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Stage DTOs
# ---------------------------------------------------------------------------

@dataclass
class StageDTO:
    id: str
    phase_id: str
    project_id: str
    name: str
    description: str
    order: int
    planned_start_date: Optional[str]
    planned_end_date: Optional[str]
    planned_duration_days: Optional[int]
    actual_start_date: Optional[str]
    actual_end_date: Optional[str]
    actual_duration_days: Optional[int]
    baseline_start_date: Optional[str]
    baseline_end_date: Optional[str]
    baseline_duration_days: Optional[int]
    status: str
    progress_pct: float
    comments: str
    deviation_days: Optional[int]
    deviation_status: Optional[str]
    updated_at: str


@dataclass
class StageDependencyDTO:
    id: str
    project_id: str
    predecessor_stage_id: str
    successor_stage_id: str
    dependency_type: str


@dataclass
class StageDeviationSummaryDTO:
    on_baseline: int
    ahead: int
    delayed: int


# ---------------------------------------------------------------------------
# Gantt DTO
# ---------------------------------------------------------------------------

@dataclass
class GanttPhaseDTO:
    """A phase row in the Gantt view, containing its child stage rows."""
    id: str
    name: str
    order: int
    overall_progress_pct: float
    planned_start_date: Optional[str]
    planned_end_date: Optional[str]
    stages: List[StageDTO]
    dependencies: List[StageDependencyDTO]


@dataclass
class GanttDataDTO:
    """Full Gantt view for a project."""
    project_id: str
    project_name: str
    overall_progress_pct: float
    total_planned_duration_days: int
    total_actual_duration_days: int
    total_baseline_duration_days: int
    active_baseline_id: Optional[str]
    phases: List[GanttPhaseDTO]
    deviation_summary: StageDeviationSummaryDTO


# ---------------------------------------------------------------------------
# Baseline DTOs
# ---------------------------------------------------------------------------

@dataclass
class BaselineDTO:
    id: str
    project_id: str
    version_number: int
    set_by_id: str
    set_at: str
    is_active: bool
    notes: str
    change_request_id: Optional[str]


@dataclass
class BaselineSnapshotDTO:
    stage_id: str
    stage_name: str
    baseline_start_date: Optional[str]
    baseline_end_date: Optional[str]
    baseline_duration_days: Optional[int]
    current_planned_end_date: Optional[str]
    deviation_days: Optional[int]
    deviation_status: Optional[str]


@dataclass
class BaselineReportDTO:
    project_id: str
    project_name: str
    overall_progress_pct: float
    active_baseline_version: Optional[int]
    active_baseline_set_at: Optional[str]
    active_baseline_notes: Optional[str]
    stage_snapshots: List[BaselineSnapshotDTO]
    baseline_history: List[BaselineDTO]
    audit_trail: List["AuditEntryDTO"]
    deviation_summary: StageDeviationSummaryDTO


# ---------------------------------------------------------------------------
# Change Request DTOs
# ---------------------------------------------------------------------------

@dataclass
class ChangeRequestDTO:
    id: str
    project_id: str
    requested_by_id: str
    approver_id: Optional[str]
    change_type: str
    reason: str
    schedule_impact_days: int
    cost_impact: Optional[float]
    status: str
    stakeholder_comments: str
    reviewer_comments: str
    submitted_at: str
    reviewed_at: Optional[str]
    updated_at: str


# ---------------------------------------------------------------------------
# Audit DTOs
# ---------------------------------------------------------------------------

@dataclass
class AuditEntryDTO:
    id: str
    sequence_number: int
    occurred_at: str
    change_type: str
    reason: str
    schedule_impact_days: int
    stakeholder_comments: str
    reviewer_comments: str
    changed_by_id: str
    approved_by_id: Optional[str]
    baseline_id: str
    change_request_id: Optional[str]


# ---------------------------------------------------------------------------
# Notification DTO
# ---------------------------------------------------------------------------

@dataclass
class NotificationLogDTO:
    id: str
    project_id: str
    stakeholder_id: str
    notification_type: str
    role_at_time: str
    comments: str
    change_request_id: Optional[str]
    baseline_id: Optional[str]
    stage_id: Optional[str]
    notified_at: str


# ===========================================================================
# DTO ASSEMBLERS
# ===========================================================================

class _Assembler:
    """Converts domain model instances into DTOs."""

    @staticmethod
    def project(p: Project) -> ProjectDTO:
        return ProjectDTO(
            id=str(p.id),
            name=p.name,
            description=p.description,
            shipyard_name=p.shipyard_name,
            vessel_type=p.vessel_type,
            planned_start_date=_fmt_date(p.planned_start_date),
            planned_end_date=_fmt_date(p.planned_end_date),
            actual_start_date=_fmt_date(p.actual_start_date),
            actual_end_date=_fmt_date(p.actual_end_date),
            overall_progress_pct=round(p.overall_progress_pct, 2),
            total_planned_duration_days=p.total_planned_duration_days,
            total_actual_duration_days=p.total_actual_duration_days,
            total_baseline_duration_days=p.total_baseline_duration_days,
            active_baseline_id=str(p.active_baseline_id) if p.active_baseline_id else None,
            created_at=_fmt(p.created_at),
            updated_at=_fmt(p.updated_at),
        )

    @staticmethod
    def phase(ph: Phase) -> PhaseDTO:
        return PhaseDTO(
            id=str(ph.id),
            project_id=str(ph.project_id),
            name=ph.name,
            description=ph.description,
            order=ph.order,
            overall_progress_pct=round(ph.overall_progress_pct, 2),
            planned_start_date=_fmt_date(ph.planned_start_date),
            planned_end_date=_fmt_date(ph.planned_end_date),
            actual_start_date=_fmt_date(ph.actual_start_date),
            actual_end_date=_fmt_date(ph.actual_end_date),
            created_at=_fmt(ph.created_at),
            updated_at=_fmt(ph.updated_at),
        )

    @staticmethod
    def stage(s: Stage) -> StageDTO:
        return StageDTO(
            id=str(s.id),
            phase_id=str(s.phase_id),
            project_id=str(s.project_id),
            name=s.name,
            description=s.description,
            order=s.order,
            planned_start_date=_fmt_date(s.planned_start_date),
            planned_end_date=_fmt_date(s.planned_end_date),
            planned_duration_days=s.planned_duration_days,
            actual_start_date=_fmt_date(s.actual_start_date),
            actual_end_date=_fmt_date(s.actual_end_date),
            actual_duration_days=s.actual_duration_days,
            baseline_start_date=_fmt_date(s.baseline_start_date),
            baseline_end_date=_fmt_date(s.baseline_end_date),
            baseline_duration_days=s.baseline_duration_days,
            status=s.status.value,
            progress_pct=round(s.progress_pct, 2),
            comments=s.comments,
            deviation_days=s.deviation_days,
            deviation_status=s.deviation_status.value if s.deviation_status else None,
            updated_at=_fmt(s.updated_at),
        )

    @staticmethod
    def dependency(d: StageDependency) -> StageDependencyDTO:
        return StageDependencyDTO(
            id=str(d.id),
            project_id=str(d.project_id),
            predecessor_stage_id=str(d.predecessor_stage_id),
            successor_stage_id=str(d.successor_stage_id),
            dependency_type=d.dependency_type,
        )

    @staticmethod
    def baseline(b: Baseline) -> BaselineDTO:
        return BaselineDTO(
            id=str(b.id),
            project_id=str(b.project_id),
            version_number=b.version_number,
            set_by_id=str(b.set_by_id),
            set_at=_fmt(b.set_at),
            is_active=b.is_active,
            notes=b.notes,
            change_request_id=str(b.change_request_id) if b.change_request_id else None,
        )

    @staticmethod
    def change_request(cr: ChangeRequest) -> ChangeRequestDTO:
        return ChangeRequestDTO(
            id=str(cr.id),
            project_id=str(cr.project_id),
            requested_by_id=str(cr.requested_by_id),
            approver_id=str(cr.approver_id) if cr.approver_id else None,
            change_type=cr.change_type.value,
            reason=cr.reason,
            schedule_impact_days=cr.schedule_impact_days,
            cost_impact=cr.cost_impact,
            status=cr.status.value,
            stakeholder_comments=cr.stakeholder_comments,
            reviewer_comments=cr.reviewer_comments,
            submitted_at=_fmt(cr.submitted_at),
            reviewed_at=_fmt(cr.reviewed_at),
            updated_at=_fmt(cr.updated_at),
        )

    @staticmethod
    def audit_entry(e: AuditTrailEntry) -> AuditEntryDTO:
        return AuditEntryDTO(
            id=str(e.id),
            sequence_number=e.sequence_number,
            occurred_at=_fmt(e.occurred_at),
            change_type=e.change_type.value,
            reason=e.reason,
            schedule_impact_days=e.schedule_impact_days,
            stakeholder_comments=e.stakeholder_comments,
            reviewer_comments=e.reviewer_comments,
            changed_by_id=str(e.changed_by_id),
            approved_by_id=str(e.approved_by_id) if e.approved_by_id else None,
            baseline_id=str(e.baseline_id),
            change_request_id=str(e.change_request_id) if e.change_request_id else None,
        )

    @staticmethod
    def notification(n: NotificationLog) -> NotificationLogDTO:
        return NotificationLogDTO(
            id=str(n.id),
            project_id=str(n.project_id),
            stakeholder_id=str(n.stakeholder_id),
            notification_type=n.notification_type.value,
            role_at_time=n.role_at_time_of_notification.value,
            comments=n.comments,
            change_request_id=str(n.change_request_id) if n.change_request_id else None,
            baseline_id=str(n.baseline_id) if n.baseline_id else None,
            stage_id=str(n.stage_id) if n.stage_id else None,
            notified_at=_fmt(n.notified_at),
        )

    @staticmethod
    def stakeholder(s: Stakeholder) -> StakeholderDTO:
        return StakeholderDTO(
            id=str(s.id),
            full_name=s.full_name,
            email=s.email,
            is_active=s.is_active,
        )

    @staticmethod
    def project_stakeholder(
        ps: ProjectStakeholder, stakeholder: Stakeholder
    ) -> ProjectStakeholderDTO:
        return ProjectStakeholderDTO(
            id=str(ps.id),
            project_id=str(ps.project_id),
            stakeholder_id=str(ps.stakeholder_id),
            full_name=stakeholder.full_name,
            email=stakeholder.email,
            role=ps.role.value,
            assigned_at=_fmt(ps.assigned_at),
        )


# ===========================================================================
# REPOSITORY INTERFACES
# ===========================================================================

class AbstractProjectRepository(abc.ABC):
    @abc.abstractmethod
    def get(self, project_id: uuid.UUID) -> Optional[Project]: ...
    @abc.abstractmethod
    def list_all(self) -> List[Project]: ...
    @abc.abstractmethod
    def save(self, project: Project) -> None: ...


class AbstractPhaseRepository(abc.ABC):
    @abc.abstractmethod
    def get(self, phase_id: uuid.UUID) -> Optional[Phase]: ...
    @abc.abstractmethod
    def list_for_project(self, project_id: uuid.UUID) -> List[Phase]: ...
    @abc.abstractmethod
    def save(self, phase: Phase) -> None: ...
    @abc.abstractmethod
    def delete(self, phase_id: uuid.UUID) -> None: ...


class AbstractStageRepository(abc.ABC):
    @abc.abstractmethod
    def get(self, stage_id: uuid.UUID) -> Optional[Stage]: ...
    @abc.abstractmethod
    def list_for_project(self, project_id: uuid.UUID) -> List[Stage]: ...
    @abc.abstractmethod
    def list_for_phase(self, phase_id: uuid.UUID) -> List[Stage]: ...
    @abc.abstractmethod
    def save(self, stage: Stage) -> None: ...
    @abc.abstractmethod
    def delete(self, stage_id: uuid.UUID) -> None: ...


class AbstractStageDependencyRepository(abc.ABC):
    @abc.abstractmethod
    def list_for_project(self, project_id: uuid.UUID) -> List[StageDependency]: ...
    @abc.abstractmethod
    def save(self, dependency: StageDependency) -> None: ...
    @abc.abstractmethod
    def delete(self, dependency_id: uuid.UUID) -> None: ...


class AbstractStageStatusUpdateRepository(abc.ABC):
    @abc.abstractmethod
    def save(self, update: StageStatusUpdate) -> None: ...
    @abc.abstractmethod
    def list_for_stage(self, stage_id: uuid.UUID) -> List[StageStatusUpdate]: ...


class AbstractStakeholderRepository(abc.ABC):
    @abc.abstractmethod
    def get(self, stakeholder_id: uuid.UUID) -> Optional[Stakeholder]: ...
    @abc.abstractmethod
    def get_by_email(self, email: str) -> Optional[Stakeholder]: ...
    @abc.abstractmethod
    def list_all(self) -> List[Stakeholder]: ...
    @abc.abstractmethod
    def save(self, stakeholder: Stakeholder) -> None: ...


class AbstractProjectStakeholderRepository(abc.ABC):
    @abc.abstractmethod
    def list_for_project(self, project_id: uuid.UUID) -> List[ProjectStakeholder]: ...
    @abc.abstractmethod
    def save(self, ps: ProjectStakeholder) -> None: ...
    @abc.abstractmethod
    def delete(self, ps_id: uuid.UUID) -> None: ...


class AbstractBaselineRepository(abc.ABC):
    @abc.abstractmethod
    def get(self, baseline_id: uuid.UUID) -> Optional[Baseline]: ...
    @abc.abstractmethod
    def list_for_project(self, project_id: uuid.UUID) -> List[Baseline]: ...
    @abc.abstractmethod
    def save(self, baseline: Baseline) -> None: ...


class AbstractBaselineStageSnapshotRepository(abc.ABC):
    @abc.abstractmethod
    def list_for_baseline(self, baseline_id: uuid.UUID) -> List[BaselineStageSnapshot]: ...
    @abc.abstractmethod
    def save(self, snapshot: BaselineStageSnapshot) -> None: ...


class AbstractChangeRequestRepository(abc.ABC):
    @abc.abstractmethod
    def get(self, cr_id: uuid.UUID) -> Optional[ChangeRequest]: ...
    @abc.abstractmethod
    def list_for_project(self, project_id: uuid.UUID) -> List[ChangeRequest]: ...
    @abc.abstractmethod
    def save(self, cr: ChangeRequest) -> None: ...


class AbstractAuditTrailRepository(abc.ABC):
    @abc.abstractmethod
    def list_for_project(self, project_id: uuid.UUID) -> List[AuditTrailEntry]: ...
    @abc.abstractmethod
    def save(self, entry: AuditTrailEntry) -> None: ...


class AbstractNotificationLogRepository(abc.ABC):
    @abc.abstractmethod
    def list_for_project(self, project_id: uuid.UUID) -> List[NotificationLog]: ...
    @abc.abstractmethod
    def list_for_stakeholder(self, stakeholder_id: uuid.UUID) -> List[NotificationLog]: ...
    @abc.abstractmethod
    def save(self, log: NotificationLog) -> None: ...


# ===========================================================================
# UNIT OF WORK
# ===========================================================================

class AbstractUnitOfWork(abc.ABC):
    """
    Groups all repositories under a single transactional boundary.
    Use as a context manager:

        with uow:
            uow.projects.save(project)
            uow.commit()
    """
    projects: AbstractProjectRepository
    phases: AbstractPhaseRepository
    stages: AbstractStageRepository
    dependencies: AbstractStageDependencyRepository
    stage_updates: AbstractStageStatusUpdateRepository
    stakeholders: AbstractStakeholderRepository
    project_stakeholders: AbstractProjectStakeholderRepository
    baselines: AbstractBaselineRepository
    baseline_snapshots: AbstractBaselineStageSnapshotRepository
    change_requests: AbstractChangeRequestRepository
    audit_trail: AbstractAuditTrailRepository
    notifications: AbstractNotificationLogRepository

    def __enter__(self) -> "AbstractUnitOfWork":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.rollback()
        else:
            self.commit()

    @abc.abstractmethod
    def commit(self) -> None: ...

    @abc.abstractmethod
    def rollback(self) -> None: ...


# ===========================================================================
# SERVICE SINGLETONS (shared across use cases)
# ===========================================================================

_project_svc = ProjectService()
_phase_svc = PhaseService()
_stage_svc = StageService()
_dep_svc = DependencyService()
_baseline_svc = BaselineService()
_change_svc = ChangeControlService()
_audit_svc = AuditService()
_notification_svc = NotificationService()
_stakeholder_svc = StakeholderService()


# ===========================================================================
# USE CASE HELPERS
# ===========================================================================

def _get_project_or_raise(uow: AbstractUnitOfWork, project_id: uuid.UUID) -> Project:
    project = uow.projects.get(project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found.")
    return project


def _get_project_stakeholders(
    uow: AbstractUnitOfWork, project_id: uuid.UUID
) -> List[ProjectStakeholder]:
    return uow.project_stakeholders.list_for_project(project_id)


def _get_stage_or_raise(uow: AbstractUnitOfWork, stage_id: uuid.UUID) -> Stage:
    stage = uow.stages.get(stage_id)
    if stage is None:
        raise NotFoundError(f"Stage {stage_id} not found.")
    return stage


def _get_change_request_or_raise(
    uow: AbstractUnitOfWork, cr_id: uuid.UUID
) -> ChangeRequest:
    cr = uow.change_requests.get(cr_id)
    if cr is None:
        raise NotFoundError(f"ChangeRequest {cr_id} not found.")
    return cr


def _refresh_project_progress(
    uow: AbstractUnitOfWork, project: Project
) -> Project:
    """Recompute and persist updated project-level summary."""
    stages = uow.stages.list_for_project(project.id)
    project = _project_svc.recalculate_progress(project, stages)
    uow.projects.save(project)
    return project


def _broadcast_and_save(
    uow: AbstractUnitOfWork,
    project_id: uuid.UUID,
    notification_type: NotificationType,
    comments: str = "",
    change_request_id: Optional[uuid.UUID] = None,
    baseline_id: Optional[uuid.UUID] = None,
    stage_id: Optional[uuid.UUID] = None,
) -> None:
    """Fire-and-save notifications to all project stakeholders."""
    ps_list = _get_project_stakeholders(uow, project_id)
    logs = _notification_svc.notify_all_stakeholders(
        project_id=project_id,
        project_stakeholders=ps_list,
        notification_type=notification_type,
        comments=comments,
        change_request_id=change_request_id,
        baseline_id=baseline_id,
        stage_id=stage_id,
    )
    for log in logs:
        uow.notifications.save(log)


# ===========================================================================
# USE CASES — PROJECT MANAGEMENT
# ===========================================================================

@dataclass
class CreateProjectCommand:
    name: str
    description: str
    shipyard_name: str
    vessel_type: str
    planned_start_date: Optional[date]
    planned_end_date: Optional[date]
    acting_user_id: uuid.UUID


class CreateProjectUseCase:
    """
    Create a new hull fabrication project and register the creator as
    Lead Project Manager.
    """

    def execute(self, cmd: CreateProjectCommand, uow: AbstractUnitOfWork) -> ProjectDTO:
        with uow:
            # Ensure the acting user exists
            actor = uow.stakeholders.get(cmd.acting_user_id)
            if actor is None:
                raise NotFoundError(f"Stakeholder {cmd.acting_user_id} not found.")

            project = _project_svc.create_project(
                name=cmd.name,
                description=cmd.description,
                shipyard_name=cmd.shipyard_name,
                vessel_type=cmd.vessel_type,
                planned_start_date=cmd.planned_start_date,
                planned_end_date=cmd.planned_end_date,
                created_by_id=cmd.acting_user_id,
            )
            uow.projects.save(project)

            # Auto-assign creator as Lead PM
            ps = _stakeholder_svc.assign_to_project(
                project_id=project.id,
                stakeholder_id=cmd.acting_user_id,
                role=StakeholderRole.LEAD_PROJECT_MANAGER,
                existing_assignments=[],
                acting_user_id=cmd.acting_user_id,
            )
            uow.project_stakeholders.save(ps)
            uow.commit()
            return _Assembler.project(project)


@dataclass
class UpdateProjectCommand:
    project_id: uuid.UUID
    acting_user_id: uuid.UUID
    name: Optional[str] = None
    description: Optional[str] = None
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None


class UpdateProjectUseCase:
    def execute(self, cmd: UpdateProjectCommand, uow: AbstractUnitOfWork) -> ProjectDTO:
        with uow:
            project = _get_project_or_raise(uow, cmd.project_id)
            ps_list = _get_project_stakeholders(uow, cmd.project_id)
            # Only Lead PM may update project-level schedule fields
            try:
                from services import _require_role
                _require_role(ps_list, cmd.acting_user_id, StakeholderRole.LEAD_PROJECT_MANAGER)
            except ValueError as exc:
                raise AuthorizationError(str(exc)) from exc

            project = _project_svc.update_project(
                project,
                name=cmd.name,
                description=cmd.description,
                planned_start_date=cmd.planned_start_date,
                planned_end_date=cmd.planned_end_date,
            )
            uow.projects.save(project)
            uow.commit()
            return _Assembler.project(project)


class GetProjectUseCase:
    def execute(self, project_id: uuid.UUID, uow: AbstractUnitOfWork) -> ProjectDTO:
        with uow:
            project = _get_project_or_raise(uow, project_id)
            return _Assembler.project(project)


class ListProjectsUseCase:
    def execute(self, uow: AbstractUnitOfWork) -> List[ProjectDTO]:
        with uow:
            return [_Assembler.project(p) for p in uow.projects.list_all()]


# ===========================================================================
# USE CASES — STAKEHOLDER MANAGEMENT
# ===========================================================================

@dataclass
class CreateStakeholderCommand:
    full_name: str
    email: str
    acting_user_id: uuid.UUID


class CreateStakeholderUseCase:
    def execute(self, cmd: CreateStakeholderCommand, uow: AbstractUnitOfWork) -> StakeholderDTO:
        with uow:
            existing = uow.stakeholders.get_by_email(cmd.email)
            if existing is not None:
                raise ApplicationError(f"A stakeholder with email '{cmd.email}' already exists.")
            stakeholder = _stakeholder_svc.create_stakeholder(
                full_name=cmd.full_name,
                email=cmd.email,
            )
            uow.stakeholders.save(stakeholder)
            uow.commit()
            return _Assembler.stakeholder(stakeholder)


class GetStakeholderUseCase:
    def execute(self, stakeholder_id: uuid.UUID, uow: AbstractUnitOfWork) -> StakeholderDTO:
        with uow:
            s = uow.stakeholders.get(stakeholder_id)
            if s is None:
                raise NotFoundError(f"Stakeholder {stakeholder_id} not found.")
            return _Assembler.stakeholder(s)


class ListStakeholdersUseCase:
    def execute(self, uow: AbstractUnitOfWork) -> List[StakeholderDTO]:
        with uow:
            return [_Assembler.stakeholder(s) for s in uow.stakeholders.list_all()]


@dataclass
class AssignStakeholderCommand:
    project_id: uuid.UUID
    stakeholder_id: uuid.UUID
    role: StakeholderRole
    acting_user_id: uuid.UUID


class AssignStakeholderUseCase:
    def execute(self, cmd: AssignStakeholderCommand, uow: AbstractUnitOfWork) -> ProjectStakeholderDTO:
        with uow:
            _get_project_or_raise(uow, cmd.project_id)
            stakeholder = uow.stakeholders.get(cmd.stakeholder_id)
            if stakeholder is None:
                raise NotFoundError(f"Stakeholder {cmd.stakeholder_id} not found.")
            existing = _get_project_stakeholders(uow, cmd.project_id)
            try:
                ps = _stakeholder_svc.assign_to_project(
                    project_id=cmd.project_id,
                    stakeholder_id=cmd.stakeholder_id,
                    role=cmd.role,
                    existing_assignments=existing,
                    acting_user_id=cmd.acting_user_id,
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc
            uow.project_stakeholders.save(ps)
            uow.commit()
            return _Assembler.project_stakeholder(ps, stakeholder)


@dataclass
class RemoveStakeholderCommand:
    project_id: uuid.UUID
    stakeholder_id: uuid.UUID
    role: StakeholderRole
    acting_user_id: uuid.UUID


class RemoveStakeholderUseCase:
    def execute(self, cmd: RemoveStakeholderCommand, uow: AbstractUnitOfWork) -> None:
        with uow:
            existing = _get_project_stakeholders(uow, cmd.project_id)
            try:
                ps = _stakeholder_svc.remove_from_project(
                    stakeholder_id=cmd.stakeholder_id,
                    role=cmd.role,
                    existing_assignments=existing,
                )
            except ValueError as exc:
                raise NotFoundError(str(exc)) from exc
            uow.project_stakeholders.delete(ps.id)
            uow.commit()


class ListProjectStakeholdersUseCase:
    def execute(self, project_id: uuid.UUID, uow: AbstractUnitOfWork) -> List[ProjectStakeholderDTO]:
        with uow:
            _get_project_or_raise(uow, project_id)
            ps_list = _get_project_stakeholders(uow, project_id)
            result = []
            for ps in ps_list:
                s = uow.stakeholders.get(ps.stakeholder_id)
                if s:
                    result.append(_Assembler.project_stakeholder(ps, s))
            return result


# ===========================================================================
# USE CASES — PHASE MANAGEMENT
# ===========================================================================

@dataclass
class AddPhaseCommand:
    project_id: uuid.UUID
    name: str
    description: str
    order: int
    acting_user_id: uuid.UUID


class AddPhaseUseCase:
    def execute(self, cmd: AddPhaseCommand, uow: AbstractUnitOfWork) -> PhaseDTO:
        with uow:
            _get_project_or_raise(uow, cmd.project_id)
            ps_list = _get_project_stakeholders(uow, cmd.project_id)
            try:
                phase = _phase_svc.add_phase(
                    project_id=cmd.project_id,
                    name=cmd.name,
                    description=cmd.description,
                    order=cmd.order,
                    project_stakeholders=ps_list,
                    acting_user_id=cmd.acting_user_id,
                )
            except ValueError as exc:
                raise AuthorizationError(str(exc)) from exc
            uow.phases.save(phase)
            uow.commit()
            return _Assembler.phase(phase)


class ListPhasesUseCase:
    def execute(self, project_id: uuid.UUID, uow: AbstractUnitOfWork) -> List[PhaseDTO]:
        with uow:
            _get_project_or_raise(uow, project_id)
            phases = uow.phases.list_for_project(project_id)
            return [_Assembler.phase(ph) for ph in sorted(phases, key=lambda p: p.order)]


@dataclass
class ReorderPhasesCommand:
    project_id: uuid.UUID
    ordered_phase_ids: List[uuid.UUID]
    acting_user_id: uuid.UUID


class ReorderPhasesUseCase:
    def execute(self, cmd: ReorderPhasesCommand, uow: AbstractUnitOfWork) -> List[PhaseDTO]:
        with uow:
            _get_project_or_raise(uow, cmd.project_id)
            ps_list = _get_project_stakeholders(uow, cmd.project_id)
            phases = uow.phases.list_for_project(cmd.project_id)
            try:
                updated = _phase_svc.reorder_phases(
                    phases=phases,
                    ordered_ids=cmd.ordered_phase_ids,
                    project_stakeholders=ps_list,
                    acting_user_id=cmd.acting_user_id,
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc
            for ph in updated:
                uow.phases.save(ph)
            uow.commit()
            return [_Assembler.phase(ph) for ph in updated]


@dataclass
class RemovePhaseCommand:
    project_id: uuid.UUID
    phase_id: uuid.UUID
    acting_user_id: uuid.UUID


class RemovePhaseUseCase:
    def execute(self, cmd: RemovePhaseCommand, uow: AbstractUnitOfWork) -> None:
        with uow:
            phase = uow.phases.get(cmd.phase_id)
            if phase is None:
                raise NotFoundError(f"Phase {cmd.phase_id} not found.")
            ps_list = _get_project_stakeholders(uow, cmd.project_id)
            stages = uow.stages.list_for_phase(cmd.phase_id)
            try:
                _phase_svc.remove_phase(
                    phase=phase,
                    stages=stages,
                    project_stakeholders=ps_list,
                    acting_user_id=cmd.acting_user_id,
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc
            for stage in stages:
                uow.stages.delete(stage.id)
            uow.phases.delete(cmd.phase_id)
            uow.commit()


# ===========================================================================
# USE CASES — STAGE MANAGEMENT
# ===========================================================================

@dataclass
class AddStageCommand:
    project_id: uuid.UUID
    phase_id: uuid.UUID
    name: str
    description: str
    order: int
    planned_start_date: Optional[date]
    planned_end_date: Optional[date]
    acting_user_id: uuid.UUID


class AddStageUseCase:
    def execute(self, cmd: AddStageCommand, uow: AbstractUnitOfWork) -> StageDTO:
        with uow:
            _get_project_or_raise(uow, cmd.project_id)
            phase = uow.phases.get(cmd.phase_id)
            if phase is None:
                raise NotFoundError(f"Phase {cmd.phase_id} not found.")
            ps_list = _get_project_stakeholders(uow, cmd.project_id)
            try:
                stage = _stage_svc.add_stage(
                    phase_id=cmd.phase_id,
                    project_id=cmd.project_id,
                    name=cmd.name,
                    description=cmd.description,
                    order=cmd.order,
                    planned_start_date=cmd.planned_start_date,
                    planned_end_date=cmd.planned_end_date,
                    project_stakeholders=ps_list,
                    acting_user_id=cmd.acting_user_id,
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc
            uow.stages.save(stage)
            # Refresh phase and project summaries
            all_phase_stages = uow.stages.list_for_phase(cmd.phase_id)
            phase = _phase_svc.recalculate_phase_progress(phase, all_phase_stages)
            uow.phases.save(phase)
            project = _get_project_or_raise(uow, cmd.project_id)
            _refresh_project_progress(uow, project)
            uow.commit()
            return _Assembler.stage(stage)


class ListStagesUseCase:
    def execute(
        self,
        project_id: uuid.UUID,
        uow: AbstractUnitOfWork,
        phase_id: Optional[uuid.UUID] = None,
    ) -> List[StageDTO]:
        with uow:
            if phase_id:
                stages = uow.stages.list_for_phase(phase_id)
            else:
                stages = uow.stages.list_for_project(project_id)
            stages = _stage_svc.compute_deviations_for_project(stages)
            return [_Assembler.stage(s) for s in sorted(stages, key=lambda s: (s.phase_id.int, s.order))]


class GetStageUseCase:
    def execute(self, stage_id: uuid.UUID, uow: AbstractUnitOfWork) -> StageDTO:
        with uow:
            stage = _get_stage_or_raise(uow, stage_id)
            _stage_svc.compute_deviation(stage)
            return _Assembler.stage(stage)


@dataclass
class UpdateStageScheduleCommand:
    stage_id: uuid.UUID
    project_id: uuid.UUID
    planned_start_date: Optional[date]
    planned_end_date: Optional[date]
    acting_user_id: uuid.UUID


class UpdateStageScheduleUseCase:
    def execute(self, cmd: UpdateStageScheduleCommand, uow: AbstractUnitOfWork) -> StageDTO:
        with uow:
            stage = _get_stage_or_raise(uow, cmd.stage_id)
            ps_list = _get_project_stakeholders(uow, cmd.project_id)
            try:
                stage = _stage_svc.update_stage_schedule(
                    stage=stage,
                    planned_start_date=cmd.planned_start_date,
                    planned_end_date=cmd.planned_end_date,
                    project_stakeholders=ps_list,
                    acting_user_id=cmd.acting_user_id,
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc
            _stage_svc.compute_deviation(stage)
            uow.stages.save(stage)
            uow.commit()
            return _Assembler.stage(stage)


@dataclass
class UpdateStageProgressCommand:
    stage_id: uuid.UUID
    project_id: uuid.UUID
    new_status: StageStatus
    new_progress_pct: float
    actual_start_date: Optional[date]
    actual_end_date: Optional[date]
    comments: str
    acting_user_id: uuid.UUID


class UpdateStageProgressUseCase:
    def execute(self, cmd: UpdateStageProgressCommand, uow: AbstractUnitOfWork) -> StageDTO:
        with uow:
            stage = _get_stage_or_raise(uow, cmd.stage_id)
            try:
                stage, status_update = _stage_svc.apply_progress_update(
                    stage=stage,
                    new_status=cmd.new_status,
                    new_progress_pct=cmd.new_progress_pct,
                    actual_start_date=cmd.actual_start_date,
                    actual_end_date=cmd.actual_end_date,
                    comments=cmd.comments,
                    acting_user_id=cmd.acting_user_id,
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc
            _stage_svc.compute_deviation(stage)
            uow.stages.save(stage)
            uow.stage_updates.save(status_update)
            # Notify if stage is blocked
            if cmd.new_status == StageStatus.BLOCKED:
                _broadcast_and_save(
                    uow,
                    project_id=cmd.project_id,
                    notification_type=NotificationType.STAGE_BLOCKED,
                    comments=cmd.comments,
                    stage_id=cmd.stage_id,
                )
            # Refresh phase and project summaries
            phase = uow.phases.get(stage.phase_id)
            if phase:
                phase_stages = uow.stages.list_for_phase(stage.phase_id)
                phase = _phase_svc.recalculate_phase_progress(phase, phase_stages)
                uow.phases.save(phase)
            project = _get_project_or_raise(uow, cmd.project_id)
            _refresh_project_progress(uow, project)
            uow.commit()
            return _Assembler.stage(stage)


# ===========================================================================
# USE CASES — STAGE DEPENDENCIES
# ===========================================================================

@dataclass
class AddStageDependencyCommand:
    project_id: uuid.UUID
    predecessor_stage_id: uuid.UUID
    successor_stage_id: uuid.UUID
    acting_user_id: uuid.UUID


class AddStageDependencyUseCase:
    def execute(self, cmd: AddStageDependencyCommand, uow: AbstractUnitOfWork) -> StageDependencyDTO:
        with uow:
            _get_project_or_raise(uow, cmd.project_id)
            ps_list = _get_project_stakeholders(uow, cmd.project_id)
            existing_deps = uow.dependencies.list_for_project(cmd.project_id)
            try:
                dep = _dep_svc.add_dependency(
                    project_id=cmd.project_id,
                    predecessor_stage_id=cmd.predecessor_stage_id,
                    successor_stage_id=cmd.successor_stage_id,
                    existing_dependencies=existing_deps,
                    project_stakeholders=ps_list,
                    acting_user_id=cmd.acting_user_id,
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc
            uow.dependencies.save(dep)
            uow.commit()
            return _Assembler.dependency(dep)


class ListStageDependenciesUseCase:
    def execute(self, project_id: uuid.UUID, uow: AbstractUnitOfWork) -> List[StageDependencyDTO]:
        with uow:
            _get_project_or_raise(uow, project_id)
            deps = uow.dependencies.list_for_project(project_id)
            return [_Assembler.dependency(d) for d in deps]


@dataclass
class RemoveStageDependencyCommand:
    project_id: uuid.UUID
    dependency_id: uuid.UUID
    acting_user_id: uuid.UUID


class RemoveStageDependencyUseCase:
    def execute(self, cmd: RemoveStageDependencyCommand, uow: AbstractUnitOfWork) -> None:
        with uow:
            all_deps = uow.dependencies.list_for_project(cmd.project_id)
            dep = next((d for d in all_deps if d.id == cmd.dependency_id), None)
            if dep is None:
                raise NotFoundError(f"Dependency {cmd.dependency_id} not found.")
            ps_list = _get_project_stakeholders(uow, cmd.project_id)
            try:
                _dep_svc.remove_dependency(
                    dependency=dep,
                    project_stakeholders=ps_list,
                    acting_user_id=cmd.acting_user_id,
                )
            except ValueError as exc:
                raise AuthorizationError(str(exc)) from exc
            uow.dependencies.delete(cmd.dependency_id)
            uow.commit()


# ===========================================================================
# USE CASES — GANTT
# ===========================================================================

class GetGanttDataUseCase:
    def execute(self, project_id: uuid.UUID, uow: AbstractUnitOfWork) -> GanttDataDTO:
        with uow:
            project = _get_project_or_raise(uow, project_id)
            phases = sorted(
                uow.phases.list_for_project(project_id), key=lambda p: p.order
            )
            all_stages = uow.stages.list_for_project(project_id)
            all_stages = _stage_svc.compute_deviations_for_project(all_stages)
            all_deps = uow.dependencies.list_for_project(project_id)

            stage_map: Dict[uuid.UUID, List[Stage]] = {}
            for s in all_stages:
                stage_map.setdefault(s.phase_id, []).append(s)

            dep_map: Dict[uuid.UUID, List[StageDependency]] = {}
            for d in all_deps:
                dep_map.setdefault(d.predecessor_stage_id, []).append(d)

            gantt_phases = []
            for ph in phases:
                ph_stages = sorted(stage_map.get(ph.id, []), key=lambda s: s.order)
                ph_deps = [
                    d for d in all_deps
                    if d.predecessor_stage_id in {s.id for s in ph_stages}
                    or d.successor_stage_id in {s.id for s in ph_stages}
                ]
                gantt_phases.append(
                    GanttPhaseDTO(
                        id=str(ph.id),
                        name=ph.name,
                        order=ph.order,
                        overall_progress_pct=round(ph.overall_progress_pct, 2),
                        planned_start_date=_fmt_date(ph.planned_start_date),
                        planned_end_date=_fmt_date(ph.planned_end_date),
                        stages=[_Assembler.stage(s) for s in ph_stages],
                        dependencies=[_Assembler.dependency(d) for d in ph_deps],
                    )
                )

            dev_summary = _stage_svc.deviation_summary(all_stages)
            return GanttDataDTO(
                project_id=str(project.id),
                project_name=project.name,
                overall_progress_pct=round(project.overall_progress_pct, 2),
                total_planned_duration_days=project.total_planned_duration_days,
                total_actual_duration_days=project.total_actual_duration_days,
                total_baseline_duration_days=project.total_baseline_duration_days,
                active_baseline_id=str(project.active_baseline_id) if project.active_baseline_id else None,
                phases=gantt_phases,
                deviation_summary=StageDeviationSummaryDTO(
                    on_baseline=dev_summary[DeviationStatus.ON_BASELINE],
                    ahead=dev_summary[DeviationStatus.AHEAD],
                    delayed=dev_summary[DeviationStatus.DELAYED],
                ),
            )


# ===========================================================================
# USE CASES — BASELINE MANAGEMENT
# ===========================================================================

@dataclass
class SetInitialBaselineCommand:
    project_id: uuid.UUID
    change_request_id: uuid.UUID
    notes: str
    acting_user_id: uuid.UUID


class SetInitialBaselineUseCase:
    def execute(self, cmd: SetInitialBaselineCommand, uow: AbstractUnitOfWork) -> BaselineDTO:
        with uow:
            project = _get_project_or_raise(uow, cmd.project_id)
            cr = _get_change_request_or_raise(uow, cmd.change_request_id)
            stages = uow.stages.list_for_project(cmd.project_id)
            existing_entries = uow.audit_trail.list_for_project(cmd.project_id)
            try:
                baseline, snapshots, updated_stages = _baseline_svc.set_initial_baseline(
                    project=project,
                    stages=stages,
                    change_request=cr,
                    set_by_id=cmd.acting_user_id,
                    notes=cmd.notes,
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc

            uow.baselines.save(baseline)
            for snap in snapshots:
                uow.baseline_snapshots.save(snap)
            for stage in updated_stages:
                uow.stages.save(stage)
            uow.projects.save(project)

            # Audit entry
            audit_entry = _audit_svc.record_baseline_change(
                project_id=cmd.project_id,
                baseline=baseline,
                change_request=cr,
                existing_entries=existing_entries,
            )
            uow.audit_trail.save(audit_entry)

            # Notifications
            _broadcast_and_save(
                uow,
                project_id=cmd.project_id,
                notification_type=NotificationType.BASELINE_SET,
                comments=cmd.notes,
                baseline_id=baseline.id,
                change_request_id=cr.id,
            )
            uow.commit()
            return _Assembler.baseline(baseline)


@dataclass
class ResetBaselineCommand:
    project_id: uuid.UUID
    change_request_id: uuid.UUID
    notes: str
    acting_user_id: uuid.UUID


class ResetBaselineUseCase:
    def execute(self, cmd: ResetBaselineCommand, uow: AbstractUnitOfWork) -> BaselineDTO:
        with uow:
            project = _get_project_or_raise(uow, cmd.project_id)
            cr = _get_change_request_or_raise(uow, cmd.change_request_id)
            stages = uow.stages.list_for_project(cmd.project_id)
            previous_baselines = uow.baselines.list_for_project(cmd.project_id)
            ps_list = _get_project_stakeholders(uow, cmd.project_id)
            existing_entries = uow.audit_trail.list_for_project(cmd.project_id)
            try:
                new_baseline, snapshots, updated_stages, updated_baselines = (
                    _baseline_svc.reset_baseline(
                        project=project,
                        stages=stages,
                        previous_baselines=previous_baselines,
                        change_request=cr,
                        set_by_id=cmd.acting_user_id,
                        notes=cmd.notes,
                        project_stakeholders=ps_list,
                    )
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc

            for b in updated_baselines:
                uow.baselines.save(b)
            uow.baselines.save(new_baseline)
            for snap in snapshots:
                uow.baseline_snapshots.save(snap)
            for stage in updated_stages:
                uow.stages.save(stage)
            uow.projects.save(project)

            # Audit entry
            audit_entry = _audit_svc.record_baseline_change(
                project_id=cmd.project_id,
                baseline=new_baseline,
                change_request=cr,
                existing_entries=existing_entries,
            )
            uow.audit_trail.save(audit_entry)

            # Notifications
            _broadcast_and_save(
                uow,
                project_id=cmd.project_id,
                notification_type=NotificationType.BASELINE_RESET,
                comments=cmd.notes,
                baseline_id=new_baseline.id,
                change_request_id=cr.id,
            )
            uow.commit()
            return _Assembler.baseline(new_baseline)


class GetBaselineHistoryUseCase:
    def execute(self, project_id: uuid.UUID, uow: AbstractUnitOfWork) -> List[BaselineDTO]:
        with uow:
            _get_project_or_raise(uow, project_id)
            baselines = _baseline_svc.get_baseline_history(
                uow.baselines.list_for_project(project_id)
            )
            return [_Assembler.baseline(b) for b in baselines]


class GetBaselineReportUseCase:
    def execute(self, project_id: uuid.UUID, uow: AbstractUnitOfWork) -> BaselineReportDTO:
        with uow:
            project = _get_project_or_raise(uow, project_id)
            baselines = uow.baselines.list_for_project(project_id)
            stages = uow.stages.list_for_project(project_id)
            stages = _stage_svc.compute_deviations_for_project(stages)
            audit_entries = uow.audit_trail.list_for_project(project_id)

            active_baselines = [b for b in baselines if b.is_active]
            active_baseline = active_baselines[0] if active_baselines else None

            # Build stage snapshot rows
            stage_map = {s.id: s for s in stages}
            snapshot_dtos = []
            if active_baseline:
                snapshots = uow.baseline_snapshots.list_for_baseline(active_baseline.id)
                for snap in snapshots:
                    stage = stage_map.get(snap.stage_id)
                    dev_days = None
                    dev_status = None
                    if stage and stage.planned_end_date and snap.baseline_end_date:
                        dev_days = (stage.planned_end_date - snap.baseline_end_date).days
                        if dev_days > 0:
                            dev_status = DeviationStatus.DELAYED.value
                        elif dev_days < 0:
                            dev_status = DeviationStatus.AHEAD.value
                        else:
                            dev_status = DeviationStatus.ON_BASELINE.value
                    snapshot_dtos.append(
                        BaselineSnapshotDTO(
                            stage_id=str(snap.stage_id),
                            stage_name=stage.name if stage else "Unknown",
                            baseline_start_date=_fmt_date(snap.baseline_start_date),
                            baseline_end_date=_fmt_date(snap.baseline_end_date),
                            baseline_duration_days=snap.baseline_duration_days,
                            current_planned_end_date=_fmt_date(stage.planned_end_date) if stage else None,
                            deviation_days=dev_days,
                            deviation_status=dev_status,
                        )
                    )

            dev_summary = _stage_svc.deviation_summary(stages)
            audit_dtos = [_Assembler.audit_entry(e) for e in sorted(audit_entries, key=lambda e: e.sequence_number)]
            baseline_dtos = [_Assembler.baseline(b) for b in _baseline_svc.get_baseline_history(baselines)]

            return BaselineReportDTO(
                project_id=str(project.id),
                project_name=project.name,
                overall_progress_pct=round(project.overall_progress_pct, 2),
                active_baseline_version=active_baseline.version_number if active_baseline else None,
                active_baseline_set_at=_fmt(active_baseline.set_at) if active_baseline else None,
                active_baseline_notes=active_baseline.notes if active_baseline else None,
                stage_snapshots=snapshot_dtos,
                baseline_history=baseline_dtos,
                audit_trail=audit_dtos,
                deviation_summary=StageDeviationSummaryDTO(
                    on_baseline=dev_summary[DeviationStatus.ON_BASELINE],
                    ahead=dev_summary[DeviationStatus.AHEAD],
                    delayed=dev_summary[DeviationStatus.DELAYED],
                ),
            )


# ===========================================================================
# USE CASES — CHANGE CONTROL
# ===========================================================================

@dataclass
class SubmitChangeRequestCommand:
    project_id: uuid.UUID
    requested_by_id: uuid.UUID
    approver_id: uuid.UUID
    change_type: ChangeType
    reason: str
    schedule_impact_days: int
    cost_impact: Optional[float]
    stakeholder_comments: str


class SubmitChangeRequestUseCase:
    def execute(self, cmd: SubmitChangeRequestCommand, uow: AbstractUnitOfWork) -> ChangeRequestDTO:
        with uow:
            _get_project_or_raise(uow, cmd.project_id)
            approver = uow.stakeholders.get(cmd.approver_id)
            if approver is None:
                raise NotFoundError(f"Approver stakeholder {cmd.approver_id} not found.")
            try:
                cr = _change_svc.submit_change_request(
                    project_id=cmd.project_id,
                    requested_by_id=cmd.requested_by_id,
                    approver_id=cmd.approver_id,
                    change_type=cmd.change_type,
                    reason=cmd.reason,
                    schedule_impact_days=cmd.schedule_impact_days,
                    stakeholder_comments=cmd.stakeholder_comments,
                    cost_impact=cmd.cost_impact,
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc
            uow.change_requests.save(cr)
            _broadcast_and_save(
                uow,
                project_id=cmd.project_id,
                notification_type=NotificationType.CHANGE_REQUEST_SUBMITTED,
                comments=cmd.reason,
                change_request_id=cr.id,
            )
            uow.commit()
            return _Assembler.change_request(cr)


@dataclass
class ApproveChangeRequestCommand:
    cr_id: uuid.UUID
    project_id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewer_comments: str


class ApproveChangeRequestUseCase:
    def execute(self, cmd: ApproveChangeRequestCommand, uow: AbstractUnitOfWork) -> ChangeRequestDTO:
        with uow:
            cr = _get_change_request_or_raise(uow, cmd.cr_id)
            ps_list = _get_project_stakeholders(uow, cmd.project_id)
            try:
                cr = _change_svc.approve_change_request(
                    change_request=cr,
                    reviewer_id=cmd.reviewer_id,
                    reviewer_comments=cmd.reviewer_comments,
                    project_stakeholders=ps_list,
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc
            uow.change_requests.save(cr)
            _broadcast_and_save(
                uow,
                project_id=cmd.project_id,
                notification_type=NotificationType.CHANGE_REQUEST_APPROVED,
                comments=cmd.reviewer_comments,
                change_request_id=cr.id,
            )
            uow.commit()
            return _Assembler.change_request(cr)


@dataclass
class RejectChangeRequestCommand:
    cr_id: uuid.UUID
    project_id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewer_comments: str


class RejectChangeRequestUseCase:
    def execute(self, cmd: RejectChangeRequestCommand, uow: AbstractUnitOfWork) -> ChangeRequestDTO:
        with uow:
            cr = _get_change_request_or_raise(uow, cmd.cr_id)
            ps_list = _get_project_stakeholders(uow, cmd.project_id)
            try:
                cr = _change_svc.reject_change_request(
                    change_request=cr,
                    reviewer_id=cmd.reviewer_id,
                    reviewer_comments=cmd.reviewer_comments,
                    project_stakeholders=ps_list,
                )
            except ValueError as exc:
                raise ApplicationError(str(exc)) from exc
            uow.change_requests.save(cr)
            _broadcast_and_save(
                uow,
                project_id=cmd.project_id,
                notification_type=NotificationType.CHANGE_REQUEST_REJECTED,
                comments=cmd.reviewer_comments,
                change_request_id=cr.id,
            )
            uow.commit()
            return _Assembler.change_request(cr)


class ListChangeRequestsUseCase:
    def execute(
        self,
        project_id: uuid.UUID,
        uow: AbstractUnitOfWork,
        status_filter: Optional[str] = None,
    ) -> List[ChangeRequestDTO]:
        with uow:
            _get_project_or_raise(uow, project_id)
            crs = uow.change_requests.list_for_project(project_id)
            if status_filter:
                crs = [cr for cr in crs if cr.status.value == status_filter]
            return [_Assembler.change_request(cr) for cr in sorted(crs, key=lambda c: c.submitted_at)]


class GetChangeRequestUseCase:
    def execute(self, cr_id: uuid.UUID, uow: AbstractUnitOfWork) -> ChangeRequestDTO:
        with uow:
            cr = _get_change_request_or_raise(uow, cr_id)
            return _Assembler.change_request(cr)


# ===========================================================================
# USE CASES — AUDIT TRAIL
# ===========================================================================

class GetAuditTrailUseCase:
    def execute(self, project_id: uuid.UUID, uow: AbstractUnitOfWork) -> List[AuditEntryDTO]:
        with uow:
            _get_project_or_raise(uow, project_id)
            entries = _audit_svc.get_audit_trail(
                project_id, uow.audit_trail.list_for_project(project_id)
            )
            return [_Assembler.audit_entry(e) for e in entries]


class ExportAuditTrailUseCase:
    def execute(self, project_id: uuid.UUID, uow: AbstractUnitOfWork) -> List[Dict]:
        with uow:
            _get_project_or_raise(uow, project_id)
            return _audit_svc.export_audit_trail(
                project_id, uow.audit_trail.list_for_project(project_id)
            )


# ===========================================================================
# USE CASES — NOTIFICATIONS
# ===========================================================================

class GetNotificationLogUseCase:
    def execute(
        self,
        project_id: uuid.UUID,
        uow: AbstractUnitOfWork,
    ) -> List[NotificationLogDTO]:
        with uow:
            _get_project_or_raise(uow, project_id)
            logs = uow.notifications.list_for_project(project_id)
            return [_Assembler.notification(n) for n in logs]


class GetMyNotificationsUseCase:
    def execute(
        self,
        stakeholder_id: uuid.UUID,
        uow: AbstractUnitOfWork,
    ) -> List[NotificationLogDTO]:
        with uow:
            logs = uow.notifications.list_for_stakeholder(stakeholder_id)
            return [_Assembler.notification(n) for n in logs]