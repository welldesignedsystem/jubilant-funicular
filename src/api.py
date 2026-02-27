"""
api.py

REST API layer for the Shipyard Hull Fabrication & Assembly
Project Management System.

Framework : FastAPI
Auth      : Bearer token — the token is resolved to a Stakeholder UUID by
            the get_current_user dependency; the real token-verification
            logic lives in infrastructure (e.g. JWT / API-key lookup).
            Every endpoint receives the resolved stakeholder UUID as
            `current_user_id` and passes it to the relevant use case command.

Structure
---------
  Routers (all prefixed under /api/v1)
  ├── /stakeholders                 — stakeholder registration
  ├── /projects                     — project CRUD
  │   ├── /{project_id}/phases      — phase configuration
  │   ├── /{project_id}/stages      — stage CRUD & progress
  │   │   └── /dependencies         — stage dependency wiring
  │   ├── /{project_id}/gantt       — full Gantt view
  │   ├── /{project_id}/baselines   — baseline management
  │   ├── /{project_id}/change-requests — change control workflow
  │   ├── /{project_id}/audit       — audit trail
  │   └── /{project_id}/notifications — notification log
  └── /me/notifications             — current-user notification inbox

Error handling
--------------
  NotFoundError      → 404
  AuthorizationError → 403
  ApplicationError   → 422
  ValueError         → 422
  Unhandled          → 500 (FastAPI default)

Response envelope
-----------------
  Success  : { "data": <payload> }
  Error    : { "detail": "<message>" }

Running
-------
  uvicorn api:app --reload

Dependencies (install via pip)
-------------------------------
  fastapi>=0.110
  uvicorn[standard]>=0.29
  pydantic>=2.0
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Path, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

from infrastructure import InMemoryUnitOfWork
from application import (
    # Exceptions
    ApplicationError,
    AuthorizationError,
    NotFoundError,
    # DTOs (returned by use cases → serialised as response bodies)
    AuditEntryDTO,
    BaselineDTO,
    BaselineReportDTO,
    ChangeRequestDTO,
    GanttDataDTO,
    NotificationLogDTO,
    PhaseDTO,
    ProjectDTO,
    ProjectStakeholderDTO,
    StageDTO,
    StageDependencyDTO,
    StakeholderDTO,
    # Use-case commands
    CreateProjectCommand,
    UpdateProjectCommand,
    # Use-case classes
    CreateProjectUseCase,
    UpdateProjectUseCase,
    AbstractUnitOfWork,
)
from model import ChangeType, StageStatus, StakeholderRole

# System user UUID used when no auth is required
SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")



# ---------------------------------------------------------------------------
# App bootstrap
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Shipyard Hull Fabrication & Assembly — Project Management API",
    version="1.0.0",
    description=(
        "REST API for managing hull fabrication projects: phases, stages, "
        "Gantt scheduling, baseline management, change control, audit trail, "
        "and stakeholder notifications."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def seed_system_user():
    """
    Ensure the SYSTEM_USER stakeholder exists in the in-memory store
    so all no-auth commands that reference acting_user_id can resolve it.
    """
    from infrastructure import InMemoryUnitOfWork
    from model import Stakeholder
    uow = InMemoryUnitOfWork()
    existing = uow.stakeholders.get(SYSTEM_USER_ID)
    if existing is None:
        system_user = Stakeholder(
            id=SYSTEM_USER_ID,
            full_name="System User",
            email="system@shipyard.internal",
            is_active=True,
        )
        uow.stakeholders.save(system_user)
        print(f"[startup] System stakeholder seeded: {SYSTEM_USER_ID}")


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(NotFoundError)
async def not_found_handler(request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(AuthorizationError)
async def authorization_handler(request, exc: AuthorizationError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(ApplicationError)
async def application_error_handler(request, exc: ApplicationError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_uow() -> AbstractUnitOfWork:
    """Returns the in-memory Unit of Work (no database required)."""
    return InMemoryUnitOfWork()


# ---------------------------------------------------------------------------
# Envelope helper
# ---------------------------------------------------------------------------

def _ok(data: Any) -> Dict:
    """Wrap a DTO or list of DTOs in the standard success envelope."""
    if hasattr(data, "__dataclass_fields__"):
        import dataclasses
        return {"data": dataclasses.asdict(data)}
    if isinstance(data, list):
        import dataclasses
        return {
            "data": [
                dataclasses.asdict(item) if hasattr(item, "__dataclass_fields__") else item
                for item in data
            ]
        }
    return {"data": data}


# ===========================================================================
# REQUEST BODY SCHEMAS  (Pydantic v2)
# ===========================================================================

# ---------------------------------------------------------------------------
# Stakeholder schemas
# ---------------------------------------------------------------------------

class CreateStakeholderRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr


# ---------------------------------------------------------------------------
# Project schemas
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    shipyard_name: str = Field(..., min_length=1, max_length=200)
    vessel_type: str = Field(..., min_length=1, max_length=100)
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None


# ---------------------------------------------------------------------------
# Phase schemas
# ---------------------------------------------------------------------------

class AddPhaseRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    order: int = Field(..., ge=1)


class ReorderPhasesRequest(BaseModel):
    ordered_phase_ids: List[uuid.UUID] = Field(
        ..., min_length=1, description="All phase IDs in their desired display order."
    )


# ---------------------------------------------------------------------------
# Stage schemas
# ---------------------------------------------------------------------------

class AddStageRequest(BaseModel):
    phase_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    order: int = Field(..., ge=1)
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None


class UpdateStageScheduleRequest(BaseModel):
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None


class UpdateStageProgressRequest(BaseModel):
    status: str = Field(..., description="One of: not_started, in_progress, blocked, completed")
    progress_pct: float = Field(..., ge=0.0, le=100.0)
    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    comments: str = Field(default="")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid = {s.value for s in StageStatus}
        if v not in valid:
            raise ValueError(f"status must be one of: {sorted(valid)}")
        return v


# ---------------------------------------------------------------------------
# Dependency schemas
# ---------------------------------------------------------------------------

class AddDependencyRequest(BaseModel):
    predecessor_stage_id: uuid.UUID
    successor_stage_id: uuid.UUID


# ---------------------------------------------------------------------------
# Baseline schemas
# ---------------------------------------------------------------------------

class SetInitialBaselineRequest(BaseModel):
    change_request_id: uuid.UUID
    notes: str = Field(default="")


class ResetBaselineRequest(BaseModel):
    change_request_id: uuid.UUID
    notes: str = Field(default="")


# ---------------------------------------------------------------------------
# Change request schemas
# ---------------------------------------------------------------------------

class SubmitChangeRequestRequest(BaseModel):
    approver_id: uuid.UUID
    change_type: str = Field(
        ...,
        description=(
            "One of: initial_baseline, delay, scope_change, cost_change, other"
        ),
    )
    reason: str = Field(..., min_length=5, max_length=2000)
    schedule_impact_days: int = Field(default=0)
    cost_impact: Optional[float] = None
    stakeholder_comments: str = Field(default="")

    @field_validator("change_type")
    @classmethod
    def validate_change_type(cls, v: str) -> str:
        valid = {ct.value for ct in ChangeType}
        if v not in valid:
            raise ValueError(f"change_type must be one of: {sorted(valid)}")
        return v


class ReviewChangeRequestRequest(BaseModel):
    reviewer_comments: str = Field(..., min_length=5, max_length=2000)


# ---------------------------------------------------------------------------
# Stakeholder assignment schemas
# ---------------------------------------------------------------------------

class AssignStakeholderRequest(BaseModel):
    stakeholder_id: uuid.UUID
    role: str = Field(..., description="One of the StakeholderRole enum values.")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        valid = {r.value for r in StakeholderRole}
        if v not in valid:
            raise ValueError(f"role must be one of: {sorted(valid)}")
        return v


class RemoveStakeholderRequest(BaseModel):
    stakeholder_id: uuid.UUID
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        valid = {r.value for r in StakeholderRole}
        if v not in valid:
            raise ValueError(f"role must be one of: {sorted(valid)}")
        return v


# ===========================================================================
# ROUTERS
# ===========================================================================

api_v1 = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Stakeholders
# ---------------------------------------------------------------------------

stakeholder_router = APIRouter(prefix="/stakeholders", tags=["Stakeholders"])


@stakeholder_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new stakeholder",
    response_description="The created stakeholder.",
)
def create_stakeholder(
    body: CreateStakeholderRequest,
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    Register a new person in the system.  A stakeholder must exist before
    they can be assigned to a project.
    """
    from application import CreateStakeholderUseCase, CreateStakeholderCommand
    cmd = CreateStakeholderCommand(
        full_name=body.full_name,
        email=str(body.email),
        acting_user_id=SYSTEM_USER_ID,
    )
    result = CreateStakeholderUseCase().execute(cmd, uow)
    return _ok(result)


@stakeholder_router.get(
    "",
    summary="List all stakeholders",
)
def list_stakeholders(
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import ListStakeholdersUseCase
    result = ListStakeholdersUseCase().execute(uow)
    return _ok(result)


@stakeholder_router.get(
    "/{stakeholder_id}",
    summary="Get a stakeholder by ID",
)
def get_stakeholder(
    stakeholder_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import GetStakeholderUseCase
    result = GetStakeholderUseCase().execute(stakeholder_id, uow)
    return _ok(result)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

project_router = APIRouter(prefix="/projects", tags=["Projects"])


@project_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new hull fabrication project",
)
def create_project(
    body: CreateProjectRequest,
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    Creates the project and automatically assigns the requesting user as
    Lead Project Manager.
    """
    cmd = CreateProjectCommand(
        name=body.name,
        description=body.description,
        shipyard_name=body.shipyard_name,
        vessel_type=body.vessel_type,
        planned_start_date=body.planned_start_date,
        planned_end_date=body.planned_end_date,
        acting_user_id=SYSTEM_USER_ID,
    )
    result = CreateProjectUseCase().execute(cmd, uow)
    return _ok(result)


@project_router.get(
    "",
    summary="List all projects",
)
def list_projects(
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import ListProjectsUseCase
    result = ListProjectsUseCase().execute(uow)
    return _ok(result)


@project_router.get(
    "/{project_id}",
    summary="Get a project by ID",
)
def get_project(
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import GetProjectUseCase
    result = GetProjectUseCase().execute(project_id, uow)
    return _ok(result)


@project_router.patch(
    "/{project_id}",
    summary="Update project metadata or schedule dates",
)
def update_project(
    body: UpdateProjectRequest,
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    cmd = UpdateProjectCommand(
        project_id=project_id,
        name=body.name,
        description=body.description,
        planned_start_date=body.planned_start_date,
        planned_end_date=body.planned_end_date,
        acting_user_id=SYSTEM_USER_ID,
    )
    result = UpdateProjectUseCase().execute(cmd, uow)
    return _ok(result)


# ---------------------------------------------------------------------------
# Project Stakeholders
# ---------------------------------------------------------------------------

project_stakeholder_router = APIRouter(
    prefix="/projects/{project_id}/stakeholders",
    tags=["Project Stakeholders"],
)


@project_stakeholder_router.get(
    "",
    summary="List all stakeholders assigned to a project",
)
def list_project_stakeholders(
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import ListProjectStakeholdersUseCase
    result = ListProjectStakeholdersUseCase().execute(project_id, uow)
    return _ok(result)


@project_stakeholder_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Assign a stakeholder to a project with a role",
)
def assign_stakeholder(
    body: AssignStakeholderRequest,
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import AssignStakeholderUseCase, AssignStakeholderCommand
    cmd = AssignStakeholderCommand(
        project_id=project_id,
        stakeholder_id=body.stakeholder_id,
        role=StakeholderRole(body.role),
        acting_user_id=SYSTEM_USER_ID,
    )
    result = AssignStakeholderUseCase().execute(cmd, uow)
    return _ok(result)


@project_stakeholder_router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a stakeholder role assignment from a project",
)
def remove_stakeholder(
    body: RemoveStakeholderRequest,
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import RemoveStakeholderUseCase, RemoveStakeholderCommand
    cmd = RemoveStakeholderCommand(
        project_id=project_id,
        stakeholder_id=body.stakeholder_id,
        role=StakeholderRole(body.role),
        acting_user_id=SYSTEM_USER_ID,
    )
    RemoveStakeholderUseCase().execute(cmd, uow)


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

phase_router = APIRouter(
    prefix="/projects/{project_id}/phases",
    tags=["Phases"],
)


@phase_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Add a phase to a project",
)
def add_phase(
    body: AddPhaseRequest,
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    Phases are fully configurable.  Provide an `order` value indicating
    where in the project timeline this phase appears.
    """
    from application import AddPhaseUseCase, AddPhaseCommand
    cmd = AddPhaseCommand(
        project_id=project_id,
        name=body.name,
        description=body.description,
        order=body.order,
        acting_user_id=SYSTEM_USER_ID,
    )
    result = AddPhaseUseCase().execute(cmd, uow)
    return _ok(result)


@phase_router.get(
    "",
    summary="List all phases for a project",
)
def list_phases(
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import ListPhasesUseCase
    result = ListPhasesUseCase().execute(project_id, uow)
    return _ok(result)


@phase_router.put(
    "/order",
    summary="Reorder phases by supplying the complete ordered list of phase IDs",
)
def reorder_phases(
    body: ReorderPhasesRequest,
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import ReorderPhasesUseCase, ReorderPhasesCommand
    cmd = ReorderPhasesCommand(
        project_id=project_id,
        ordered_phase_ids=body.ordered_phase_ids,
        acting_user_id=SYSTEM_USER_ID,
    )
    result = ReorderPhasesUseCase().execute(cmd, uow)
    return _ok(result)


@phase_router.delete(
    "/{phase_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a phase and all its stages (only if no actuals recorded)",
)
def remove_phase(
    project_id: uuid.UUID = Path(...),
    phase_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import RemovePhaseUseCase, RemovePhaseCommand
    cmd = RemovePhaseCommand(
        project_id=project_id,
        phase_id=phase_id,
        acting_user_id=SYSTEM_USER_ID,
    )
    RemovePhaseUseCase().execute(cmd, uow)


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

stage_router = APIRouter(
    prefix="/projects/{project_id}/stages",
    tags=["Stages"],
)


@stage_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Add a stage to a phase within a project",
)
def add_stage(
    body: AddStageRequest,
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import AddStageUseCase, AddStageCommand
    cmd = AddStageCommand(
        project_id=project_id,
        phase_id=body.phase_id,
        name=body.name,
        description=body.description,
        order=body.order,
        planned_start_date=body.planned_start_date,
        planned_end_date=body.planned_end_date,
        acting_user_id=SYSTEM_USER_ID,
    )
    result = AddStageUseCase().execute(cmd, uow)
    return _ok(result)


@stage_router.get(
    "",
    summary="List all stages for a project",
)
def list_stages(
    project_id: uuid.UUID = Path(...),
    phase_id: Optional[uuid.UUID] = Query(default=None, description="Filter by phase"),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import ListStagesUseCase
    result = ListStagesUseCase().execute(project_id, uow, phase_id=phase_id)
    return _ok(result)


@stage_router.get(
    "/{stage_id}",
    summary="Get a single stage",
)
def get_stage(
    project_id: uuid.UUID = Path(...),
    stage_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import GetStageUseCase
    result = GetStageUseCase().execute(stage_id, uow)
    return _ok(result)


@stage_router.patch(
    "/{stage_id}/schedule",
    summary="Update a stage's planned start / end dates",
)
def update_stage_schedule(
    body: UpdateStageScheduleRequest,
    project_id: uuid.UUID = Path(...),
    stage_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import UpdateStageScheduleUseCase, UpdateStageScheduleCommand
    cmd = UpdateStageScheduleCommand(
        stage_id=stage_id,
        project_id=project_id,
        planned_start_date=body.planned_start_date,
        planned_end_date=body.planned_end_date,
        acting_user_id=SYSTEM_USER_ID,
    )
    result = UpdateStageScheduleUseCase().execute(cmd, uow)
    return _ok(result)


@stage_router.patch(
    "/{stage_id}/progress",
    summary="Update actual progress, status, and dates for a stage",
)
def update_stage_progress(
    body: UpdateStageProgressRequest,
    project_id: uuid.UUID = Path(...),
    stage_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    Used by project team members to record actual start/end dates, update
    the progress percentage (0–100), and set the stage status.  Actual end
    date cannot be set without an actual start date.
    """
    from application import UpdateStageProgressUseCase, UpdateStageProgressCommand
    cmd = UpdateStageProgressCommand(
        stage_id=stage_id,
        project_id=project_id,
        new_status=StageStatus(body.status),
        new_progress_pct=body.progress_pct,
        actual_start_date=body.actual_start_date,
        actual_end_date=body.actual_end_date,
        comments=body.comments,
        acting_user_id=SYSTEM_USER_ID,
    )
    result = UpdateStageProgressUseCase().execute(cmd, uow)
    return _ok(result)


# ---------------------------------------------------------------------------
# Stage Dependencies
# ---------------------------------------------------------------------------

dependency_router = APIRouter(
    prefix="/projects/{project_id}/stages/dependencies",
    tags=["Stage Dependencies"],
)


@dependency_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Add a Finish-to-Start dependency between two stages",
)
def add_dependency(
    body: AddDependencyRequest,
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    The system validates that no circular dependency chain would result.
    Dependency arrows are rendered on the Gantt chart to show the critical path.
    """
    from application import AddStageDependencyUseCase, AddStageDependencyCommand
    cmd = AddStageDependencyCommand(
        project_id=project_id,
        predecessor_stage_id=body.predecessor_stage_id,
        successor_stage_id=body.successor_stage_id,
        acting_user_id=SYSTEM_USER_ID,
    )
    result = AddStageDependencyUseCase().execute(cmd, uow)
    return _ok(result)


@dependency_router.get(
    "",
    summary="List all stage dependencies for a project",
)
def list_dependencies(
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import ListStageDependenciesUseCase
    result = ListStageDependenciesUseCase().execute(project_id, uow)
    return _ok(result)


@dependency_router.delete(
    "/{dependency_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a stage dependency",
)
def remove_dependency(
    project_id: uuid.UUID = Path(...),
    dependency_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import RemoveStageDependencyUseCase, RemoveStageDependencyCommand
    cmd = RemoveStageDependencyCommand(
        project_id=project_id,
        dependency_id=dependency_id,
        acting_user_id=SYSTEM_USER_ID,
    )
    RemoveStageDependencyUseCase().execute(cmd, uow)


# ---------------------------------------------------------------------------
# Gantt
# ---------------------------------------------------------------------------

gantt_router = APIRouter(
    prefix="/projects/{project_id}/gantt",
    tags=["Gantt"],
)


@gantt_router.get(
    "",
    summary="Retrieve the full Gantt chart data for a project",
)
def get_gantt(
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    Returns all phases and their child stages, including planned/actual/baseline
    dates, progress, status, deviation indicators, and dependency arrows.
    Also includes project-level progress summary and deviation counts.
    """
    from application import GetGanttDataUseCase
    result = GetGanttDataUseCase().execute(project_id, uow)
    return _ok(result)


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

baseline_router = APIRouter(
    prefix="/projects/{project_id}/baselines",
    tags=["Baseline Management"],
)


@baseline_router.post(
    "/initial",
    status_code=status.HTTP_201_CREATED,
    summary="Set the initial (version 1) baseline for a project",
)
def set_initial_baseline(
    body: SetInitialBaselineRequest,
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    Locks the current planned dates as the approved baseline.  Requires a
    pre-approved ChangeRequest of type `initial_baseline`.  All stage planned
    dates are snapshotted and become the deviation reference.
    """
    from application import SetInitialBaselineUseCase, SetInitialBaselineCommand
    cmd = SetInitialBaselineCommand(
        project_id=project_id,
        change_request_id=body.change_request_id,
        notes=body.notes,
        acting_user_id=SYSTEM_USER_ID,
    )
    result = SetInitialBaselineUseCase().execute(cmd, uow)
    return _ok(result)


@baseline_router.post(
    "/reset",
    status_code=status.HTTP_201_CREATED,
    summary="Reset the baseline following an approved change request",
)
def reset_baseline(
    body: ResetBaselineRequest,
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    Creates a new baseline version, deactivates the previous one, and
    re-snapshots all stage planned dates.  The previous baseline is retained
    in history.  Scope change baselines additionally require Owner
    Representative approval on the linked ChangeRequest.
    """
    from application import ResetBaselineUseCase, ResetBaselineCommand
    cmd = ResetBaselineCommand(
        project_id=project_id,
        change_request_id=body.change_request_id,
        notes=body.notes,
        acting_user_id=SYSTEM_USER_ID,
    )
    result = ResetBaselineUseCase().execute(cmd, uow)
    return _ok(result)


@baseline_router.get(
    "",
    summary="List all baseline versions for a project",
)
def list_baselines(
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import GetBaselineHistoryUseCase
    result = GetBaselineHistoryUseCase().execute(project_id, uow)
    return _ok(result)


@baseline_router.get(
    "/report",
    summary="Generate a full baseline deviation report for the active baseline",
)
def get_baseline_report(
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    Returns: active baseline snapshot per stage with deviation days and
    status, full baseline version history, audit trail, and deviation summary
    counts (on-baseline / ahead / delayed).
    """
    from application import GetBaselineReportUseCase
    result = GetBaselineReportUseCase().execute(project_id, uow)
    return _ok(result)


# ---------------------------------------------------------------------------
# Change Requests
# ---------------------------------------------------------------------------

change_request_router = APIRouter(
    prefix="/projects/{project_id}/change-requests",
    tags=["Change Control"],
)


@change_request_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a change request to modify the approved baseline",
)
def submit_change_request(
    body: SubmitChangeRequestRequest,
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    The change request begins in PENDING status.  The designated approver
    must call the approve or reject endpoints before any baseline modification
    can take effect.  Scope changes additionally require the approver to hold
    the Owner Representative role.
    """
    from application import SubmitChangeRequestUseCase, SubmitChangeRequestCommand
    cmd = SubmitChangeRequestCommand(
        project_id=project_id,
        approver_id=body.approver_id,
        change_type=ChangeType(body.change_type),
        reason=body.reason,
        schedule_impact_days=body.schedule_impact_days,
        cost_impact=body.cost_impact,
        stakeholder_comments=body.stakeholder_comments,
        requested_by_id=SYSTEM_USER_ID,
    )
    return _ok(result)


@change_request_router.get(
    "",
    summary="List all change requests for a project",
)
def list_change_requests(
    project_id: uuid.UUID = Path(...),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status: pending, approved, rejected",
    ),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import ListChangeRequestsUseCase
    result = ListChangeRequestsUseCase().execute(
        project_id, uow, status_filter=status_filter
    )
    return _ok(result)


@change_request_router.get(
    "/{cr_id}",
    summary="Get a single change request",
)
def get_change_request(
    project_id: uuid.UUID = Path(...),
    cr_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import GetChangeRequestUseCase
    result = GetChangeRequestUseCase().execute(cr_id, uow)
    return _ok(result)


@change_request_router.post(
    "/{cr_id}/approve",
    summary="Approve a pending change request",
)
def approve_change_request(
    body: ReviewChangeRequestRequest,
    project_id: uuid.UUID = Path(...),
    cr_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    Only the designated approver may call this endpoint.  For SCOPE_CHANGE
    requests the approver must hold the Owner Representative role.
    Reviewer comments are mandatory.
    """
    from application import ApproveChangeRequestUseCase, ApproveChangeRequestCommand
    cmd = ApproveChangeRequestCommand(
        cr_id=cr_id,
        project_id=project_id,
        reviewer_comments=body.reviewer_comments,
        reviewer_id=SYSTEM_USER_ID,
    )
    return _ok(result)


@change_request_router.post(
    "/{cr_id}/reject",
    summary="Reject a pending change request",
)
def reject_change_request(
    body: ReviewChangeRequestRequest,
    project_id: uuid.UUID = Path(...),
    cr_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """Reviewer comments are mandatory when rejecting."""
    from application import RejectChangeRequestUseCase, RejectChangeRequestCommand
    cmd = RejectChangeRequestCommand(
        cr_id=cr_id,
        project_id=project_id,
        reviewer_comments=body.reviewer_comments,
        reviewer_id=SYSTEM_USER_ID,
    )
    return _ok(result)


# ---------------------------------------------------------------------------
# Audit Trail
# ---------------------------------------------------------------------------

audit_router = APIRouter(
    prefix="/projects/{project_id}/audit",
    tags=["Audit Trail"],
)


@audit_router.get(
    "",
    summary="View the immutable audit trail for a project",
)
def get_audit_trail(
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    """
    Returns all approved baseline changes in chronological order.  Each entry
    records the sequence number, UTC timestamp, change type, reason, schedule
    impact, stakeholder and reviewer comments, and the identities of the
    submitter and approver.
    """
    from application import GetAuditTrailUseCase
    result = GetAuditTrailUseCase().execute(project_id, uow)
    return _ok(result)


@audit_router.get(
    "/export",
    summary="Export the audit trail as a serialisable list (JSON/CSV ready)",
)
def export_audit_trail(
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import ExportAuditTrailUseCase
    result = ExportAuditTrailUseCase().execute(project_id, uow)
    return _ok(result)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

notification_router = APIRouter(
    prefix="/projects/{project_id}/notifications",
    tags=["Notifications"],
)


@notification_router.get(
    "",
    summary="List all notification log entries for a project",
)
def get_project_notifications(
    project_id: uuid.UUID = Path(...),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import GetNotificationLogUseCase
    result = GetNotificationLogUseCase().execute(
        project_id=project_id, uow=uow
    )
    return _ok(result)


# ---------------------------------------------------------------------------
# Current-user inbox
# ---------------------------------------------------------------------------

me_router = APIRouter(prefix="/me", tags=["My Notifications"])


@me_router.get(
    "/notifications",
    summary="Get the notification inbox for the authenticated user",
)
def get_my_notifications(
    stakeholder_id: uuid.UUID = Query(..., description="Stakeholder UUID to fetch notifications for"),
    uow: AbstractUnitOfWork = Depends(get_uow),
):
    from application import GetMyNotificationsUseCase
    result = GetMyNotificationsUseCase().execute(stakeholder_id, uow)
    return _ok(result)


# ===========================================================================
# REGISTER ROUTERS
# ===========================================================================

api_v1.include_router(stakeholder_router)
api_v1.include_router(project_router)
api_v1.include_router(project_stakeholder_router)
api_v1.include_router(phase_router)
api_v1.include_router(stage_router)
api_v1.include_router(dependency_router)
api_v1.include_router(gantt_router)
api_v1.include_router(baseline_router)
api_v1.include_router(change_request_router)
api_v1.include_router(audit_router)
api_v1.include_router(notification_router)
api_v1.include_router(me_router)

app.include_router(api_v1)

# ---------------------------------------------------------------------------
# MCP Server — exposes all API routes as MCP tools
# Accessible at: http://localhost:8000/mcp
# ---------------------------------------------------------------------------
mcp = FastApiMCP(app)
mcp.mount()


# ===========================================================================
# HEALTH CHECK
# ===========================================================================

@app.get("/health", tags=["Health"], summary="Service health check")
def health():
    return {"status": "ok"}


# ===========================================================================
# OPENAPI CUSTOMISATION — tag order and descriptions
# ===========================================================================

tags_metadata = [
    {
        "name": "Health",
        "description": "Liveness probe.",
    },
    {
        "name": "Stakeholders",
        "description": (
            "Register people who participate in or receive notifications about projects. "
            "A stakeholder must be created here before being assigned to a project."
        ),
    },
    {
        "name": "Projects",
        "description": (
            "Top-level hull fabrication project management.  Creating a project "
            "automatically assigns the requesting user as Lead Project Manager."
        ),
    },
    {
        "name": "Project Stakeholders",
        "description": (
            "Assign or remove stakeholders from a project.  A stakeholder may hold "
            "multiple roles on the same project."
        ),
    },
    {
        "name": "Phases",
        "description": (
            "Configurable project phases (e.g. Fabrication Preparation, Block Assembly). "
            "Phases may be added, removed, and reordered without system-level changes."
        ),
    },
    {
        "name": "Stages",
        "description": (
            "Individual work activities within a phase.  Each stage tracks its own "
            "planned, actual, and baseline schedule plus progress percentage and status."
        ),
    },
    {
        "name": "Stage Dependencies",
        "description": (
            "Finish-to-Start dependencies between stages.  Used to render the critical "
            "path on the Gantt chart.  The system prevents circular chains."
        ),
    },
    {
        "name": "Gantt",
        "description": (
            "Aggregated Gantt view including all phases, stages, dependencies, "
            "deviation indicators, and project-level progress summary."
        ),
    },
    {
        "name": "Baseline Management",
        "description": (
            "Set or reset the approved project baseline.  All stage planned dates are "
            "snapshotted and serve as the immutable deviation reference.  Full version "
            "history is retained.  A pre-approved ChangeRequest is required."
        ),
    },
    {
        "name": "Change Control",
        "description": (
            "Formal change request workflow.  No baseline modification is permitted "
            "without an approved change request.  Scope changes additionally require "
            "Owner Representative approval."
        ),
    },
    {
        "name": "Audit Trail",
        "description": (
            "Immutable, append-only log of every approved baseline change.  "
            "Exportable for governance and external reporting."
        ),
    },
    {
        "name": "Notifications",
        "description": (
            "Structured stakeholder communication log.  Entries are created "
            "automatically on baseline changes, stage blocks, delays, and "
            "change request state transitions."
        ),
    },
    {
        "name": "My Notifications",
        "description": "Current-user notification inbox across all projects.",
    },
]

app.openapi_tags = tags_metadata