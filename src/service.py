"""
services.py

Service layer for the Shipyard Hull Fabrication & Assembly
Project Management System.

Responsibilities
----------------
Each service class encapsulates all business logic for its domain.
Services receive and return domain model instances (from models.py).
No persistence is handled here — callers are responsible for storing
and retrieving models via a repository / ORM layer of their choosing.

Services
--------
- ProjectService          – Project CRUD and overall progress calculation
- PhaseService            – Phase configuration (add / reorder / remove)
- StageService            – Stage CRUD, progress updates, deviation computation
- DependencyService       – Stage dependency management
- BaselineService         – Baseline creation, reset, history and reporting
- ChangeControlService    – Change request workflow and approval enforcement
- AuditService            – Audit trail retrieval and export helpers
- NotificationService     – Notification log creation and query helpers
- StakeholderService      – Stakeholder and project-role management

Design notes
------------
- All mutating methods accept the acting user's stakeholder_id and stamp
  updated_at / updated_by fields accordingly.
- UTC datetimes are used throughout; callers must pass tz-aware values.
- Business rule violations raise a ValueError with a descriptive message.
- Authorization checks (role enforcement) are declared as guard helpers
  and called at the start of each operation that requires elevated rights.
- Methods that would normally persist data return the mutated object(s)
  so the caller can hand them to a repository.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_role(
    project_stakeholders: List[ProjectStakeholder],
    stakeholder_id: uuid.UUID,
    *allowed_roles: StakeholderRole,
) -> None:
    """Raise ValueError if the stakeholder does not hold one of the allowed roles."""
    roles = {
        ps.role
        for ps in project_stakeholders
        if ps.stakeholder_id == stakeholder_id
    }
    if not roles.intersection(allowed_roles):
        raise ValueError(
            f"Stakeholder {stakeholder_id} does not hold any of the required "
            f"roles: {[r.value for r in allowed_roles]}."
        )


# ---------------------------------------------------------------------------
# ProjectService
# ---------------------------------------------------------------------------

class ProjectService:
    """
    Manages project creation and top-level schedule summary fields.
    """

    def create_project(
        self,
        name: str,
        description: str,
        shipyard_name: str,
        vessel_type: str,
        planned_start_date: Optional[date],
        planned_end_date: Optional[date],
        created_by_id: uuid.UUID,
    ) -> Project:
        """Create and return a new Project instance (unsaved)."""
        if planned_start_date and planned_end_date and planned_end_date < planned_start_date:
            raise ValueError("planned_end_date must not be before planned_start_date.")
        return Project(
            name=name,
            description=description,
            shipyard_name=shipyard_name,
            vessel_type=vessel_type,
            planned_start_date=planned_start_date,
            planned_end_date=planned_end_date,
            created_by_id=created_by_id,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )

    def update_project(
        self,
        project: Project,
        name: Optional[str] = None,
        description: Optional[str] = None,
        planned_start_date: Optional[date] = None,
        planned_end_date: Optional[date] = None,
    ) -> Project:
        """Apply field-level updates to a project."""
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        if planned_start_date is not None:
            project.planned_start_date = planned_start_date
        if planned_end_date is not None:
            project.planned_end_date = planned_end_date
        if (
            project.planned_start_date
            and project.planned_end_date
            and project.planned_end_date < project.planned_start_date
        ):
            raise ValueError("planned_end_date must not be before planned_start_date.")
        project.updated_at = _utcnow()
        return project

    def recalculate_progress(self, project: Project, stages: List[Stage]) -> Project:
        """
        Recompute overall_progress_pct and duration summary fields from all
        active stage records.  Call this after any stage progress update.

        Overall progress is the simple mean of all stage progress percentages.
        Duration fields sum each stage's respective duration in days.
        """
        if not stages:
            project.overall_progress_pct = 0.0
            project.total_planned_duration_days = 0
            project.total_actual_duration_days = 0
            project.total_baseline_duration_days = 0
            project.updated_at = _utcnow()
            return project

        project.overall_progress_pct = sum(s.progress_pct for s in stages) / len(stages)
        project.total_planned_duration_days = sum(
            s.planned_duration_days or 0 for s in stages
        )
        project.total_actual_duration_days = sum(
            s.actual_duration_days or 0 for s in stages
        )
        project.total_baseline_duration_days = sum(
            s.baseline_duration_days or 0 for s in stages
        )
        project.updated_at = _utcnow()
        return project


# ---------------------------------------------------------------------------
# PhaseService
# ---------------------------------------------------------------------------

class PhaseService:
    """
    Manages phase configuration within a project.
    Phases may be freely added, reordered, and removed by authorized users.
    """

    def add_phase(
        self,
        project_id: uuid.UUID,
        name: str,
        description: str,
        order: int,
        project_stakeholders: List[ProjectStakeholder],
        acting_user_id: uuid.UUID,
    ) -> Phase:
        """Create and return a new Phase (unsaved)."""
        _require_role(
            project_stakeholders,
            acting_user_id,
            StakeholderRole.LEAD_PROJECT_MANAGER,
        )
        return Phase(
            project_id=project_id,
            name=name,
            description=description,
            order=order,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )

    def reorder_phases(
        self,
        phases: List[Phase],
        ordered_ids: List[uuid.UUID],
        project_stakeholders: List[ProjectStakeholder],
        acting_user_id: uuid.UUID,
    ) -> List[Phase]:
        """
        Re-assign `order` values to phases according to the provided id sequence.
        Returns the updated list sorted by new order.
        """
        _require_role(
            project_stakeholders,
            acting_user_id,
            StakeholderRole.LEAD_PROJECT_MANAGER,
        )
        id_to_phase: Dict[uuid.UUID, Phase] = {p.id: p for p in phases}
        if set(ordered_ids) != set(id_to_phase.keys()):
            raise ValueError("ordered_ids must contain exactly the ids of all existing phases.")
        for i, phase_id in enumerate(ordered_ids, start=1):
            id_to_phase[phase_id].order = i
            id_to_phase[phase_id].updated_at = _utcnow()
        return sorted(phases, key=lambda p: p.order)

    def remove_phase(
        self,
        phase: Phase,
        stages: List[Stage],
        project_stakeholders: List[ProjectStakeholder],
        acting_user_id: uuid.UUID,
    ) -> Tuple[Phase, List[Stage]]:
        """
        Mark a phase for removal and return it along with its child stages.
        Callers are responsible for cascading the deletion in the repository.
        Raises ValueError if any stage in the phase has recorded actuals
        (completed work must not be silently discarded).
        """
        _require_role(
            project_stakeholders,
            acting_user_id,
            StakeholderRole.LEAD_PROJECT_MANAGER,
        )
        phases_stages = [s for s in stages if s.phase_id == phase.id]
        for stage in phases_stages:
            if stage.actual_start_date is not None:
                raise ValueError(
                    f"Cannot remove phase '{phase.name}': stage '{stage.name}' "
                    "has recorded actual progress."
                )
        return phase, phases_stages

    def recalculate_phase_progress(self, phase: Phase, stages: List[Stage]) -> Phase:
        """Recompute phase-level summary dates and progress from child stages."""
        phase_stages = [s for s in stages if s.phase_id == phase.id]
        if not phase_stages:
            phase.overall_progress_pct = 0.0
            phase.updated_at = _utcnow()
            return phase

        phase.overall_progress_pct = sum(s.progress_pct for s in phase_stages) / len(phase_stages)

        planned_starts = [s.planned_start_date for s in phase_stages if s.planned_start_date]
        planned_ends = [s.planned_end_date for s in phase_stages if s.planned_end_date]
        actual_starts = [s.actual_start_date for s in phase_stages if s.actual_start_date]
        actual_ends = [s.actual_end_date for s in phase_stages if s.actual_end_date]

        phase.planned_start_date = min(planned_starts) if planned_starts else None
        phase.planned_end_date = max(planned_ends) if planned_ends else None
        phase.actual_start_date = min(actual_starts) if actual_starts else None
        phase.actual_end_date = max(actual_ends) if actual_ends else None
        phase.updated_at = _utcnow()
        return phase


# ---------------------------------------------------------------------------
# StageService
# ---------------------------------------------------------------------------

class StageService:
    """
    Manages individual stage lifecycle: creation, updates, and deviation maths.
    """

    # --- CRUD ---------------------------------------------------------------

    def add_stage(
        self,
        phase_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
        description: str,
        order: int,
        planned_start_date: Optional[date],
        planned_end_date: Optional[date],
        project_stakeholders: List[ProjectStakeholder],
        acting_user_id: uuid.UUID,
    ) -> Stage:
        """Create and return a new Stage (unsaved)."""
        _require_role(
            project_stakeholders,
            acting_user_id,
            StakeholderRole.LEAD_PROJECT_MANAGER,
        )
        planned_duration = None
        if planned_start_date and planned_end_date:
            if planned_end_date < planned_start_date:
                raise ValueError("planned_end_date must not be before planned_start_date.")
            planned_duration = (planned_end_date - planned_start_date).days

        return Stage(
            phase_id=phase_id,
            project_id=project_id,
            name=name,
            description=description,
            order=order,
            planned_start_date=planned_start_date,
            planned_end_date=planned_end_date,
            planned_duration_days=planned_duration,
            status=StageStatus.NOT_STARTED,
            progress_pct=0.0,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )

    def update_stage_schedule(
        self,
        stage: Stage,
        planned_start_date: Optional[date],
        planned_end_date: Optional[date],
        project_stakeholders: List[ProjectStakeholder],
        acting_user_id: uuid.UUID,
    ) -> Stage:
        """Update a stage's planned schedule dates."""
        _require_role(
            project_stakeholders,
            acting_user_id,
            StakeholderRole.LEAD_PROJECT_MANAGER,
        )
        if planned_start_date and planned_end_date and planned_end_date < planned_start_date:
            raise ValueError("planned_end_date must not be before planned_start_date.")
        stage.planned_start_date = planned_start_date
        stage.planned_end_date = planned_end_date
        if planned_start_date and planned_end_date:
            stage.planned_duration_days = (planned_end_date - planned_start_date).days
        stage.updated_at = _utcnow()
        stage.updated_by_id = acting_user_id
        return stage

    # --- Progress updates ---------------------------------------------------

    def apply_progress_update(
        self,
        stage: Stage,
        new_status: StageStatus,
        new_progress_pct: float,
        actual_start_date: Optional[date],
        actual_end_date: Optional[date],
        comments: str,
        acting_user_id: uuid.UUID,
    ) -> Tuple[Stage, StageStatusUpdate]:
        """
        Apply a progress/status update to a stage and produce an audit record.

        Business rules enforced:
        - actual_end_date requires actual_start_date.
        - progress_pct must be in [0, 100].
        - A COMPLETED stage must have both actual_start_date and actual_end_date.
        """
        if not (0.0 <= new_progress_pct <= 100.0):
            raise ValueError("progress_pct must be between 0 and 100.")
        if actual_end_date and not actual_start_date:
            raise ValueError("actual_end_date cannot be set without actual_start_date.")
        if new_status == StageStatus.COMPLETED and (
            actual_start_date is None or actual_end_date is None
        ):
            raise ValueError(
                "A stage cannot be marked COMPLETED without both actual_start_date "
                "and actual_end_date."
            )

        update = StageStatusUpdate(
            stage_id=stage.id,
            project_id=stage.project_id,
            updated_by_id=acting_user_id,
            previous_status=stage.status,
            new_status=new_status,
            previous_progress_pct=stage.progress_pct,
            new_progress_pct=new_progress_pct,
            actual_start_date=actual_start_date,
            actual_end_date=actual_end_date,
            comments=comments,
            updated_at=_utcnow(),
        )

        # Apply to stage
        stage.status = new_status
        stage.progress_pct = new_progress_pct
        stage.actual_start_date = actual_start_date
        stage.actual_end_date = actual_end_date
        if actual_start_date and actual_end_date:
            stage.actual_duration_days = (actual_end_date - actual_start_date).days
        stage.comments = comments
        stage.updated_at = _utcnow()
        stage.updated_by_id = acting_user_id

        return stage, update

    # --- Deviation ----------------------------------------------------------

    def compute_deviation(self, stage: Stage) -> Stage:
        """
        Calculate and set deviation_days and deviation_status on the stage.
        Uses planned_end_date vs. baseline_end_date.
        """
        if stage.planned_end_date is None or stage.baseline_end_date is None:
            stage.deviation_days = None
            stage.deviation_status = None
            return stage

        delta = (stage.planned_end_date - stage.baseline_end_date).days
        stage.deviation_days = delta
        if delta > 0:
            stage.deviation_status = DeviationStatus.DELAYED
        elif delta < 0:
            stage.deviation_status = DeviationStatus.AHEAD
        else:
            stage.deviation_status = DeviationStatus.ON_BASELINE
        return stage

    def compute_deviations_for_project(self, stages: List[Stage]) -> List[Stage]:
        """Recompute deviations for all stages in a project."""
        return [self.compute_deviation(s) for s in stages]

    def deviation_summary(
        self, stages: List[Stage]
    ) -> Dict[DeviationStatus, int]:
        """
        Return a count of stages in each deviation state.
        Stages without a baseline are excluded from the summary.
        """
        summary: Dict[DeviationStatus, int] = {
            DeviationStatus.ON_BASELINE: 0,
            DeviationStatus.AHEAD: 0,
            DeviationStatus.DELAYED: 0,
        }
        for stage in stages:
            if stage.deviation_status is not None:
                summary[stage.deviation_status] += 1
        return summary


# ---------------------------------------------------------------------------
# DependencyService
# ---------------------------------------------------------------------------

class DependencyService:
    """
    Manages predecessor/successor dependencies between stages.
    """

    def add_dependency(
        self,
        project_id: uuid.UUID,
        predecessor_stage_id: uuid.UUID,
        successor_stage_id: uuid.UUID,
        existing_dependencies: List[StageDependency],
        project_stakeholders: List[ProjectStakeholder],
        acting_user_id: uuid.UUID,
    ) -> StageDependency:
        """
        Create a new Finish-to-Start dependency.

        Raises ValueError if:
        - The dependency already exists.
        - A self-loop is detected.
        - Adding the dependency would create a cycle.
        """
        _require_role(
            project_stakeholders,
            acting_user_id,
            StakeholderRole.LEAD_PROJECT_MANAGER,
        )
        if predecessor_stage_id == successor_stage_id:
            raise ValueError("A stage cannot depend on itself.")

        for dep in existing_dependencies:
            if (
                dep.predecessor_stage_id == predecessor_stage_id
                and dep.successor_stage_id == successor_stage_id
            ):
                raise ValueError("This dependency already exists.")

        if self._would_create_cycle(
            predecessor_stage_id, successor_stage_id, existing_dependencies
        ):
            raise ValueError(
                "Adding this dependency would create a circular dependency chain."
            )

        return StageDependency(
            project_id=project_id,
            predecessor_stage_id=predecessor_stage_id,
            successor_stage_id=successor_stage_id,
            created_at=_utcnow(),
        )

    def remove_dependency(
        self,
        dependency: StageDependency,
        project_stakeholders: List[ProjectStakeholder],
        acting_user_id: uuid.UUID,
    ) -> StageDependency:
        """Return the dependency marked for removal (caller deletes from store)."""
        _require_role(
            project_stakeholders,
            acting_user_id,
            StakeholderRole.LEAD_PROJECT_MANAGER,
        )
        return dependency

    def _would_create_cycle(
        self,
        new_predecessor_id: uuid.UUID,
        new_successor_id: uuid.UUID,
        existing_dependencies: List[StageDependency],
    ) -> bool:
        """
        Detect cycles using DFS from new_successor_id.
        If we can reach new_predecessor_id by following successors, adding the
        new dependency would create a cycle.
        """
        adjacency: Dict[uuid.UUID, List[uuid.UUID]] = {}
        for dep in existing_dependencies:
            adjacency.setdefault(dep.predecessor_stage_id, []).append(dep.successor_stage_id)

        visited: set = set()
        stack = [new_successor_id]
        while stack:
            node = stack.pop()
            if node == new_predecessor_id:
                return True
            if node in visited:
                continue
            visited.add(node)
            stack.extend(adjacency.get(node, []))
        return False


# ---------------------------------------------------------------------------
# BaselineService
# ---------------------------------------------------------------------------

class BaselineService:
    """
    Manages baseline creation, reset, history, and snapshot generation.

    A baseline may only be set or reset via this service.  The first baseline
    requires a ChangeRequest of type INITIAL_BASELINE; all subsequent baselines
    require an APPROVED ChangeRequest of the appropriate type.
    """

    def set_initial_baseline(
        self,
        project: Project,
        stages: List[Stage],
        change_request: ChangeRequest,
        set_by_id: uuid.UUID,
        notes: str = "",
    ) -> Tuple[Baseline, List[BaselineStageSnapshot], List[Stage]]:
        """
        Set the first (version 1) baseline for a project.

        Returns the new Baseline, its stage snapshots, and the updated Stage list
        with baseline dates populated.
        """
        if change_request.status != ChangeRequestStatus.APPROVED:
            raise ValueError("Cannot set baseline: change request is not approved.")
        if change_request.change_type != ChangeType.INITIAL_BASELINE:
            raise ValueError("Initial baseline requires a change request of type INITIAL_BASELINE.")
        if project.active_baseline_id is not None:
            raise ValueError(
                "Project already has a baseline. Use reset_baseline for subsequent baselines."
            )

        baseline = Baseline(
            project_id=project.id,
            version_number=1,
            set_by_id=set_by_id,
            set_at=_utcnow(),
            is_active=True,
            notes=notes,
            change_request_id=change_request.id,
        )
        snapshots, updated_stages = self._snapshot_stages(baseline, stages)
        project.active_baseline_id = baseline.id
        return baseline, snapshots, updated_stages

    def reset_baseline(
        self,
        project: Project,
        stages: List[Stage],
        previous_baselines: List[Baseline],
        change_request: ChangeRequest,
        set_by_id: uuid.UUID,
        notes: str = "",
        project_stakeholders: Optional[List[ProjectStakeholder]] = None,
    ) -> Tuple[Baseline, List[BaselineStageSnapshot], List[Stage], List[Baseline]]:
        """
        Create a new approved baseline, deactivating the previous active baseline.

        For SCOPE_CHANGE requests, validates that the approver holds the
        OWNER_REPRESENTATIVE role (passed via project_stakeholders).

        Returns new Baseline, its snapshots, updated stages, and updated
        previous baselines list (with old active baseline deactivated).
        """
        if change_request.status != ChangeRequestStatus.APPROVED:
            raise ValueError("Cannot reset baseline: change request is not approved.")
        if project.active_baseline_id is None:
            raise ValueError("No active baseline found. Use set_initial_baseline first.")

        # Scope change requires Owner Representative approval
        if change_request.change_type == ChangeType.SCOPE_CHANGE:
            if project_stakeholders is None or change_request.approver_id is None:
                raise ValueError(
                    "SCOPE_CHANGE baseline reset requires project_stakeholders and a designated approver."
                )
            _require_role(
                project_stakeholders,
                change_request.approver_id,
                StakeholderRole.OWNER_REPRESENTATIVE,
            )

        next_version = max((b.version_number for b in previous_baselines), default=0) + 1

        # Deactivate current active baseline
        updated_previous: List[Baseline] = []
        for b in previous_baselines:
            if b.is_active:
                b.is_active = False
            updated_previous.append(b)

        new_baseline = Baseline(
            project_id=project.id,
            version_number=next_version,
            set_by_id=set_by_id,
            set_at=_utcnow(),
            is_active=True,
            notes=notes,
            change_request_id=change_request.id,
        )
        snapshots, updated_stages = self._snapshot_stages(new_baseline, stages)
        project.active_baseline_id = new_baseline.id
        return new_baseline, snapshots, updated_stages, updated_previous

    def get_baseline_history(
        self, baselines: List[Baseline]
    ) -> List[Baseline]:
        """Return all baselines sorted by version number ascending."""
        return sorted(baselines, key=lambda b: b.version_number)

    def get_snapshot_for_baseline(
        self,
        baseline_id: uuid.UUID,
        all_snapshots: List[BaselineStageSnapshot],
    ) -> List[BaselineStageSnapshot]:
        """Return all stage snapshots belonging to a specific baseline."""
        return [s for s in all_snapshots if s.baseline_id == baseline_id]

    def generate_baseline_report(
        self,
        project: Project,
        baselines: List[Baseline],
        all_snapshots: List[BaselineStageSnapshot],
        stages: List[Stage],
        audit_entries: List[AuditTrailEntry],
    ) -> Dict:
        """
        Produce a structured baseline report dict suitable for serialisation
        to JSON / CSV / PDF by the presentation layer.

        The report includes:
        - Project summary
        - Active baseline snapshot per stage with deviations
        - Full baseline version history
        - Audit trail entries
        """
        stage_map = {s.id: s for s in stages}
        active_baselines = [b for b in baselines if b.is_active]
        active_baseline = active_baselines[0] if active_baselines else None

        active_snapshot_rows = []
        if active_baseline:
            active_snapshots = self.get_snapshot_for_baseline(
                active_baseline.id, all_snapshots
            )
            for snap in active_snapshots:
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
                active_snapshot_rows.append(
                    {
                        "stage_id": str(snap.stage_id),
                        "stage_name": stage.name if stage else "Unknown",
                        "baseline_start": snap.baseline_start_date.isoformat()
                        if snap.baseline_start_date
                        else None,
                        "baseline_end": snap.baseline_end_date.isoformat()
                        if snap.baseline_end_date
                        else None,
                        "planned_end": stage.planned_end_date.isoformat()
                        if stage and stage.planned_end_date
                        else None,
                        "deviation_days": dev_days,
                        "deviation_status": dev_status,
                    }
                )

        return {
            "project": {
                "id": str(project.id),
                "name": project.name,
                "overall_progress_pct": project.overall_progress_pct,
                "active_baseline_id": str(project.active_baseline_id)
                if project.active_baseline_id
                else None,
            },
            "active_baseline": {
                "version_number": active_baseline.version_number if active_baseline else None,
                "set_at": active_baseline.set_at.isoformat() if active_baseline else None,
                "notes": active_baseline.notes if active_baseline else None,
            },
            "stage_deviations": active_snapshot_rows,
            "baseline_history": [
                {
                    "version_number": b.version_number,
                    "set_at": b.set_at.isoformat(),
                    "is_active": b.is_active,
                    "notes": b.notes,
                }
                for b in self.get_baseline_history(baselines)
            ],
            "audit_trail": [
                {
                    "sequence_number": e.sequence_number,
                    "occurred_at": e.occurred_at.isoformat(),
                    "change_type": e.change_type.value,
                    "reason": e.reason,
                    "schedule_impact_days": e.schedule_impact_days,
                    "reviewer_comments": e.reviewer_comments,
                }
                for e in sorted(audit_entries, key=lambda x: x.sequence_number)
            ],
        }

    # --- Private helpers ----------------------------------------------------

    def _snapshot_stages(
        self,
        baseline: Baseline,
        stages: List[Stage],
    ) -> Tuple[List[BaselineStageSnapshot], List[Stage]]:
        """
        Create BaselineStageSnapshot records for every stage and write baseline
        dates back onto the Stage objects.
        """
        snapshots: List[BaselineStageSnapshot] = []
        updated_stages: List[Stage] = []
        now = _utcnow()

        for stage in stages:
            snapshot = BaselineStageSnapshot(
                baseline_id=baseline.id,
                stage_id=stage.id,
                project_id=stage.project_id,
                baseline_start_date=stage.planned_start_date,
                baseline_end_date=stage.planned_end_date,
                baseline_duration_days=stage.planned_duration_days,
                snapshotted_at=now,
            )
            snapshots.append(snapshot)

            # Write baseline dates onto the stage (read-only after this point)
            stage.baseline_start_date = stage.planned_start_date
            stage.baseline_end_date = stage.planned_end_date
            stage.baseline_duration_days = stage.planned_duration_days
            stage.updated_at = now
            updated_stages.append(stage)

        return snapshots, updated_stages


# ---------------------------------------------------------------------------
# ChangeControlService
# ---------------------------------------------------------------------------

class ChangeControlService:
    """
    Enforces the formal change request workflow.

    No baseline modification may proceed without an APPROVED ChangeRequest.
    """

    def submit_change_request(
        self,
        project_id: uuid.UUID,
        requested_by_id: uuid.UUID,
        approver_id: uuid.UUID,
        change_type: ChangeType,
        reason: str,
        schedule_impact_days: int,
        stakeholder_comments: str = "",
        cost_impact: Optional[float] = None,
    ) -> ChangeRequest:
        """Create and return a pending ChangeRequest (unsaved)."""
        if not reason.strip():
            raise ValueError("A reason must be provided for the change request.")
        return ChangeRequest(
            project_id=project_id,
            requested_by_id=requested_by_id,
            approver_id=approver_id,
            change_type=change_type,
            reason=reason,
            schedule_impact_days=schedule_impact_days,
            cost_impact=cost_impact,
            stakeholder_comments=stakeholder_comments,
            status=ChangeRequestStatus.PENDING,
            submitted_at=_utcnow(),
            updated_at=_utcnow(),
        )

    def approve_change_request(
        self,
        change_request: ChangeRequest,
        reviewer_id: uuid.UUID,
        reviewer_comments: str,
        project_stakeholders: List[ProjectStakeholder],
    ) -> ChangeRequest:
        """
        Approve a pending change request.

        The reviewer must be the designated approver.
        SCOPE_CHANGE requests additionally require the reviewer to hold the
        OWNER_REPRESENTATIVE role (enforced here and again in BaselineService).
        """
        if change_request.status != ChangeRequestStatus.PENDING:
            raise ValueError("Only PENDING change requests can be approved.")
        if change_request.approver_id != reviewer_id:
            raise ValueError("Only the designated approver may approve this change request.")
        if not reviewer_comments.strip():
            raise ValueError("Reviewer comments are mandatory for approval.")

        if change_request.change_type == ChangeType.SCOPE_CHANGE:
            _require_role(
                project_stakeholders,
                reviewer_id,
                StakeholderRole.OWNER_REPRESENTATIVE,
            )

        change_request.status = ChangeRequestStatus.APPROVED
        change_request.reviewed_at = _utcnow()
        change_request.reviewer_comments = reviewer_comments
        change_request.updated_at = _utcnow()
        return change_request

    def reject_change_request(
        self,
        change_request: ChangeRequest,
        reviewer_id: uuid.UUID,
        reviewer_comments: str,
        project_stakeholders: List[ProjectStakeholder],
    ) -> ChangeRequest:
        """Reject a pending change request."""
        if change_request.status != ChangeRequestStatus.PENDING:
            raise ValueError("Only PENDING change requests can be rejected.")
        if change_request.approver_id != reviewer_id:
            raise ValueError("Only the designated approver may reject this change request.")
        if not reviewer_comments.strip():
            raise ValueError("Reviewer comments are mandatory for rejection.")

        change_request.status = ChangeRequestStatus.REJECTED
        change_request.reviewed_at = _utcnow()
        change_request.reviewer_comments = reviewer_comments
        change_request.updated_at = _utcnow()
        return change_request

    def get_pending_requests(
        self, change_requests: List[ChangeRequest]
    ) -> List[ChangeRequest]:
        return [cr for cr in change_requests if cr.status == ChangeRequestStatus.PENDING]


# ---------------------------------------------------------------------------
# AuditService
# ---------------------------------------------------------------------------

class AuditService:
    """
    Handles creation and querying of AuditTrailEntry records.
    Entries are immutable once written.
    """

    def record_baseline_change(
        self,
        project_id: uuid.UUID,
        baseline: Baseline,
        change_request: ChangeRequest,
        existing_entries: List[AuditTrailEntry],
    ) -> AuditTrailEntry:
        """
        Write a new immutable AuditTrailEntry for an approved baseline change.
        sequence_number is auto-incremented per project.
        """
        next_seq = (
            max((e.sequence_number for e in existing_entries), default=0) + 1
        )
        return AuditTrailEntry(
            project_id=project_id,
            sequence_number=next_seq,
            baseline_id=baseline.id,
            change_request_id=change_request.id,
            changed_by_id=change_request.requested_by_id,
            approved_by_id=change_request.approver_id,
            change_type=change_request.change_type,
            reason=change_request.reason,
            schedule_impact_days=change_request.schedule_impact_days,
            stakeholder_comments=change_request.stakeholder_comments,
            reviewer_comments=change_request.reviewer_comments,
            occurred_at=_utcnow(),
        )

    def get_audit_trail(
        self,
        project_id: uuid.UUID,
        all_entries: List[AuditTrailEntry],
    ) -> List[AuditTrailEntry]:
        """Return all audit entries for a project, sorted by sequence number."""
        return sorted(
            [e for e in all_entries if e.project_id == project_id],
            key=lambda e: e.sequence_number,
        )

    def export_audit_trail(
        self,
        project_id: uuid.UUID,
        all_entries: List[AuditTrailEntry],
    ) -> List[Dict]:
        """
        Serialise the audit trail to a list of dicts for CSV/JSON export.
        """
        entries = self.get_audit_trail(project_id, all_entries)
        return [
            {
                "sequence_number": e.sequence_number,
                "occurred_at_utc": e.occurred_at.isoformat(),
                "change_type": e.change_type.value,
                "reason": e.reason,
                "schedule_impact_days": e.schedule_impact_days,
                "stakeholder_comments": e.stakeholder_comments,
                "reviewer_comments": e.reviewer_comments,
                "changed_by_id": str(e.changed_by_id),
                "approved_by_id": str(e.approved_by_id) if e.approved_by_id else None,
                "baseline_id": str(e.baseline_id),
            }
            for e in entries
        ]


# ---------------------------------------------------------------------------
# NotificationService
# ---------------------------------------------------------------------------

class NotificationService:
    """
    Creates and queries NotificationLog entries.
    Notifications are generated automatically by the system on key events.
    """

    def notify(
        self,
        project_id: uuid.UUID,
        stakeholder_id: uuid.UUID,
        role_at_time: StakeholderRole,
        notification_type: NotificationType,
        comments: str = "",
        change_request_id: Optional[uuid.UUID] = None,
        baseline_id: Optional[uuid.UUID] = None,
        stage_id: Optional[uuid.UUID] = None,
    ) -> NotificationLog:
        """Create and return a notification log entry (unsaved)."""
        return NotificationLog(
            project_id=project_id,
            stakeholder_id=stakeholder_id,
            notification_type=notification_type,
            role_at_time_of_notification=role_at_time,
            change_request_id=change_request_id,
            baseline_id=baseline_id,
            stage_id=stage_id,
            comments=comments,
            notified_at=_utcnow(),
        )

    def notify_all_stakeholders(
        self,
        project_id: uuid.UUID,
        project_stakeholders: List[ProjectStakeholder],
        notification_type: NotificationType,
        comments: str = "",
        change_request_id: Optional[uuid.UUID] = None,
        baseline_id: Optional[uuid.UUID] = None,
        stage_id: Optional[uuid.UUID] = None,
    ) -> List[NotificationLog]:
        """
        Broadcast a notification to every stakeholder on the project.
        Returns a list of NotificationLog entries (unsaved).
        """
        logs: List[NotificationLog] = []
        for ps in project_stakeholders:
            logs.append(
                self.notify(
                    project_id=project_id,
                    stakeholder_id=ps.stakeholder_id,
                    role_at_time=ps.role,
                    notification_type=notification_type,
                    comments=comments,
                    change_request_id=change_request_id,
                    baseline_id=baseline_id,
                    stage_id=stage_id,
                )
            )
        return logs

    def get_notifications_for_stakeholder(
        self,
        stakeholder_id: uuid.UUID,
        all_logs: List[NotificationLog],
    ) -> List[NotificationLog]:
        """Return all notification logs for a given stakeholder, newest first."""
        return sorted(
            [n for n in all_logs if n.stakeholder_id == stakeholder_id],
            key=lambda n: n.notified_at,
            reverse=True,
        )

    def get_notifications_for_project(
        self,
        project_id: uuid.UUID,
        all_logs: List[NotificationLog],
    ) -> List[NotificationLog]:
        """Return all notification logs for a project, newest first."""
        return sorted(
            [n for n in all_logs if n.project_id == project_id],
            key=lambda n: n.notified_at,
            reverse=True,
        )


# ---------------------------------------------------------------------------
# StakeholderService
# ---------------------------------------------------------------------------

class StakeholderService:
    """
    Manages stakeholder registration and project role assignments.
    """

    def create_stakeholder(
        self,
        full_name: str,
        email: str,
    ) -> Stakeholder:
        """Create and return a new Stakeholder (unsaved)."""
        if not full_name.strip():
            raise ValueError("Stakeholder full_name must not be empty.")
        if "@" not in email:
            raise ValueError(f"'{email}' does not appear to be a valid email address.")
        return Stakeholder(
            full_name=full_name,
            email=email,
            is_active=True,
            created_at=_utcnow(),
        )

    def assign_to_project(
        self,
        project_id: uuid.UUID,
        stakeholder_id: uuid.UUID,
        role: StakeholderRole,
        existing_assignments: List[ProjectStakeholder],
        acting_user_id: uuid.UUID,
    ) -> ProjectStakeholder:
        """
        Assign a stakeholder to a project with a given role.
        A stakeholder may hold multiple roles — duplicate role assignments
        are rejected but different roles for the same stakeholder are permitted.
        """
        for ps in existing_assignments:
            if ps.stakeholder_id == stakeholder_id and ps.role == role:
                raise ValueError(
                    f"Stakeholder {stakeholder_id} already holds role '{role.value}' on this project."
                )
        return ProjectStakeholder(
            project_id=project_id,
            stakeholder_id=stakeholder_id,
            role=role,
            assigned_at=_utcnow(),
        )

    def remove_from_project(
        self,
        stakeholder_id: uuid.UUID,
        role: StakeholderRole,
        existing_assignments: List[ProjectStakeholder],
    ) -> ProjectStakeholder:
        """
        Locate and return the ProjectStakeholder record to be removed.
        Caller is responsible for deleting from the store.
        """
        for ps in existing_assignments:
            if ps.stakeholder_id == stakeholder_id and ps.role == role:
                return ps
        raise ValueError(
            f"No assignment found for stakeholder {stakeholder_id} with role '{role.value}'."
        )

    def get_stakeholders_by_role(
        self,
        role: StakeholderRole,
        project_stakeholders: List[ProjectStakeholder],
    ) -> List[uuid.UUID]:
        """Return stakeholder IDs holding a specific role on the project."""
        return [ps.stakeholder_id for ps in project_stakeholders if ps.role == role]