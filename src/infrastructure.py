"""
infrastructure.py

In-memory implementation of all repository interfaces and the Unit of Work.

This is a self-contained, zero-dependency backend that stores everything in
plain Python dicts keyed by UUID.  It is intentionally simple — suitable for
local development, demos, and integration testing without needing a real
database.

To swap in a real database (e.g. SQLAlchemy + PostgreSQL) later, implement
the same Abstract* interfaces from application.py and override get_uow() in
api.py:

    app.dependency_overrides[get_uow] = lambda: SqlAlchemyUnitOfWork(session)

Nothing in services.py, application.py, or api.py needs to change.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from application import (
    AbstractAuditTrailRepository,
    AbstractBaselineRepository,
    AbstractBaselineStageSnapshotRepository,
    AbstractChangeRequestRepository,
    AbstractNotificationLogRepository,
    AbstractPhaseRepository,
    AbstractProjectRepository,
    AbstractProjectStakeholderRepository,
    AbstractStageDependencyRepository,
    AbstractStageRepository,
    AbstractStageStatusUpdateRepository,
    AbstractStakeholderRepository,
    AbstractUnitOfWork,
)
from model import (
    AuditTrailEntry,
    Baseline,
    BaselineStageSnapshot,
    ChangeRequest,
    NotificationLog,
    Phase,
    Project,
    ProjectStakeholder,
    Stage,
    StageDependency,
    StageStatusUpdate,
    Stakeholder,
)


# ---------------------------------------------------------------------------
# Generic in-memory store
# ---------------------------------------------------------------------------

class _Store(dict):
    """A plain dict with typed get/save/delete helpers."""

    def fetch(self, key: uuid.UUID):
        return self.get(key)

    def put(self, obj) -> None:
        self[obj.id] = obj

    def remove(self, key: uuid.UUID) -> None:
        self.pop(key, None)

    def all(self) -> list:
        return list(self.values())


# ---------------------------------------------------------------------------
# Shared in-memory database (module-level singleton)
# Persists for the lifetime of the process — restarting uvicorn resets it.
# ---------------------------------------------------------------------------

class InMemoryDatabase:
    def __init__(self):
        self.projects:             _Store = _Store()
        self.phases:               _Store = _Store()
        self.stages:               _Store = _Store()
        self.dependencies:         _Store = _Store()
        self.stage_updates:        _Store = _Store()
        self.stakeholders:         _Store = _Store()
        self.project_stakeholders: _Store = _Store()
        self.baselines:            _Store = _Store()
        self.baseline_snapshots:   _Store = _Store()
        self.change_requests:      _Store = _Store()
        self.audit_trail:          _Store = _Store()
        self.notifications:        _Store = _Store()


# Module-level singleton — shared across all requests
_db = InMemoryDatabase()


# ---------------------------------------------------------------------------
# Repository implementations
# ---------------------------------------------------------------------------

class InMemoryProjectRepository(AbstractProjectRepository):
    def __init__(self, store: _Store): self._s = store
    def get(self, project_id):        return self._s.fetch(project_id)
    def list_all(self):               return self._s.all()
    def save(self, project):          self._s.put(project)


class InMemoryPhaseRepository(AbstractPhaseRepository):
    def __init__(self, store: _Store): self._s = store
    def get(self, phase_id):          return self._s.fetch(phase_id)
    def list_for_project(self, project_id):
        return [p for p in self._s.all() if p.project_id == project_id]
    def save(self, phase):            self._s.put(phase)
    def delete(self, phase_id):       self._s.remove(phase_id)


class InMemoryStageRepository(AbstractStageRepository):
    def __init__(self, store: _Store): self._s = store
    def get(self, stage_id):          return self._s.fetch(stage_id)
    def list_for_project(self, project_id):
        return [s for s in self._s.all() if s.project_id == project_id]
    def list_for_phase(self, phase_id):
        return [s for s in self._s.all() if s.phase_id == phase_id]
    def save(self, stage):            self._s.put(stage)
    def delete(self, stage_id):       self._s.remove(stage_id)


class InMemoryStageDependencyRepository(AbstractStageDependencyRepository):
    def __init__(self, store: _Store): self._s = store
    def list_for_project(self, project_id):
        return [d for d in self._s.all() if d.project_id == project_id]
    def save(self, dep):              self._s.put(dep)
    def delete(self, dep_id):         self._s.remove(dep_id)


class InMemoryStageStatusUpdateRepository(AbstractStageStatusUpdateRepository):
    def __init__(self, store: _Store): self._s = store
    def save(self, update):           self._s.put(update)
    def list_for_stage(self, stage_id):
        return [u for u in self._s.all() if u.stage_id == stage_id]


class InMemoryStakeholderRepository(AbstractStakeholderRepository):
    def __init__(self, store: _Store): self._s = store
    def get(self, stakeholder_id):    return self._s.fetch(stakeholder_id)
    def get_by_email(self, email):
        return next((s for s in self._s.all() if s.email == email), None)
    def list_all(self):               return self._s.all()
    def save(self, stakeholder):      self._s.put(stakeholder)


class InMemoryProjectStakeholderRepository(AbstractProjectStakeholderRepository):
    def __init__(self, store: _Store): self._s = store
    def list_for_project(self, project_id):
        return [ps for ps in self._s.all() if ps.project_id == project_id]
    def save(self, ps):               self._s.put(ps)
    def delete(self, ps_id):          self._s.remove(ps_id)


class InMemoryBaselineRepository(AbstractBaselineRepository):
    def __init__(self, store: _Store): self._s = store
    def get(self, baseline_id):       return self._s.fetch(baseline_id)
    def list_for_project(self, project_id):
        return [b for b in self._s.all() if b.project_id == project_id]
    def save(self, baseline):         self._s.put(baseline)


class InMemoryBaselineStageSnapshotRepository(AbstractBaselineStageSnapshotRepository):
    def __init__(self, store: _Store): self._s = store
    def list_for_baseline(self, baseline_id):
        return [s for s in self._s.all() if s.baseline_id == baseline_id]
    def save(self, snapshot):         self._s.put(snapshot)


class InMemoryChangeRequestRepository(AbstractChangeRequestRepository):
    def __init__(self, store: _Store): self._s = store
    def get(self, cr_id):             return self._s.fetch(cr_id)
    def list_for_project(self, project_id):
        return [cr for cr in self._s.all() if cr.project_id == project_id]
    def save(self, cr):               self._s.put(cr)


class InMemoryAuditTrailRepository(AbstractAuditTrailRepository):
    def __init__(self, store: _Store): self._s = store
    def list_for_project(self, project_id):
        return [e for e in self._s.all() if e.project_id == project_id]
    def save(self, entry):            self._s.put(entry)


class InMemoryNotificationLogRepository(AbstractNotificationLogRepository):
    def __init__(self, store: _Store): self._s = store
    def list_for_project(self, project_id):
        return [n for n in self._s.all() if n.project_id == project_id]
    def list_for_stakeholder(self, stakeholder_id):
        return [n for n in self._s.all() if n.stakeholder_id == stakeholder_id]
    def save(self, log):              self._s.put(log)


# ---------------------------------------------------------------------------
# Unit of Work
# ---------------------------------------------------------------------------

class InMemoryUnitOfWork(AbstractUnitOfWork):
    """
    Wraps all in-memory repositories.  commit() and rollback() are no-ops
    because dict mutations are immediate — there is no transaction to manage.
    In a real SQL implementation, commit() would call session.commit().
    """

    def __init__(self, db: InMemoryDatabase = _db):
        self.projects             = InMemoryProjectRepository(db.projects)
        self.phases               = InMemoryPhaseRepository(db.phases)
        self.stages               = InMemoryStageRepository(db.stages)
        self.dependencies         = InMemoryStageDependencyRepository(db.dependencies)
        self.stage_updates        = InMemoryStageStatusUpdateRepository(db.stage_updates)
        self.stakeholders         = InMemoryStakeholderRepository(db.stakeholders)
        self.project_stakeholders = InMemoryProjectStakeholderRepository(db.project_stakeholders)
        self.baselines            = InMemoryBaselineRepository(db.baselines)
        self.baseline_snapshots   = InMemoryBaselineStageSnapshotRepository(db.baseline_snapshots)
        self.change_requests      = InMemoryChangeRequestRepository(db.change_requests)
        self.audit_trail          = InMemoryAuditTrailRepository(db.audit_trail)
        self.notifications        = InMemoryNotificationLogRepository(db.notifications)

    def commit(self)   -> None: pass   # no-op for in-memory
    def rollback(self) -> None: pass   # no-op for in-memory