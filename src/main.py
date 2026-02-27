"""
main.py

Entry point for the Shipyard Hull Fabrication & Assembly Project Management API.

Wires the in-memory infrastructure into the FastAPI app and starts uvicorn.

Usage
-----
    # Option 1 — run directly
    python main.py

    # Option 2 — run via uvicorn CLI (recommended for development)
    uvicorn main:app --reload --port 8000

    # Option 3 — run via uvicorn CLI on a custom host/port
    uvicorn main:app --host 0.0.0.0 --port 8080 --reload

Once running, open your browser at:
    http://localhost:8000/docs      ← Swagger UI  (try every endpoint interactively)
    http://localhost:8000/redoc     ← ReDoc
    http://localhost:8000/health    ← liveness check

Quick-start walkthrough (use Swagger UI or curl)
-------------------------------------------------
1.  POST  /api/v1/stakeholders          — create yourself as a stakeholder
                                          copy the returned "id" — this is your token
2.  POST  /api/v1/projects              — create a project
                                          Authorization: Bearer <your-stakeholder-id>
3.  POST  /api/v1/projects/{id}/phases  — add a phase
4.  POST  /api/v1/projects/{id}/stages  — add stages inside the phase
5.  POST  /api/v1/projects/{id}/change-requests   — submit an INITIAL_BASELINE request
6.  POST  /api/v1/projects/{id}/change-requests/{cr_id}/approve  — approve it
7.  POST  /api/v1/projects/{id}/baselines/initial — lock the baseline
8.  PATCH /api/v1/projects/{id}/stages/{sid}/progress — record actual progress
9.  GET   /api/v1/projects/{id}/gantt   — view the full Gantt with deviations
10. GET   /api/v1/projects/{id}/baselines/report — view baseline deviation report

Authentication note
-------------------
The default get_current_user dependency expects the raw stakeholder UUID as
the Bearer token (e.g. "Bearer 550e8400-e29b-41d4-a716-446655440000").
This is intentional for easy local testing — replace it with a real JWT
implementation before going to production.
"""

import uvicorn

from api import app, get_uow
from infrastructure import InMemoryUnitOfWork


# ---------------------------------------------------------------------------
# Wire the concrete Unit of Work into the FastAPI dependency system.
# To swap databases, replace InMemoryUnitOfWork with your SQL implementation.
# ---------------------------------------------------------------------------

app.dependency_overrides[get_uow] = lambda: InMemoryUnitOfWork()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,          # auto-reload on file changes during development
        log_level="info",
    )