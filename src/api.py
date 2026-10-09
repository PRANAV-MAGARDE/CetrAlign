"""
src/api.py
----------
FastAPI application for FinAgent.

Endpoints
~~~~~~~~~
POST   /tasks              Submit a new task (body: TaskRequest) → TaskResponse
GET    /tasks/{task_id}    Get task status & result → TaskResponse
GET    /tasks              List all tasks (summary)
GET    /health             Health check

Tasks run in the background via asyncio.create_task so the POST endpoint
returns immediately with the task_id.  Results are stored in an in-memory
dict for the lifetime of the server process.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.agent import FinAgent
from src.models import TaskRequest, TaskResponse, TaskState, TaskStatus

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

tags_metadata = [
    {
        "name": "Monitoring",
    },
    {
        "name": "Tasks",
    },
]

app = FastAPI(
    title="FinAgent – Autonomous AI Task Worker",
    description=(
        "### Welcome to the FinAgent API Dashboard\n\n"
        "An autonomous AI agent for Futures & Options finance operations. "
        "Submit natural-language tasks; FinAgent plans, executes, verifies, and reports.\n\n"
        "#### How to use:\n"
        "1. **Submit** a task using `POST /tasks`.\n"
        "2. **Poll** the status using `GET /tasks/{task_id}`.\n"
        "3. When completed, read the final evidence-backed report.\n"
    ),
    version="1.0.0",
    contact={
        "name": "FinAgent Support Team",
        "url": "https://github.com/finagent",
    },
    openapi_tags=tags_metadata,
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1,  # hide schemas section
        "displayRequestDuration": True,
        "filter": True,
        "syntaxHighlight.theme": "monokai",  # nice dark theme for code blocks
    },
)

# Allow all origins for development (tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory task store  {task_id: TaskState}
# ---------------------------------------------------------------------------

_task_store: dict[str, TaskState] = {}

# ---------------------------------------------------------------------------
# Singleton agent (initialised at startup)
# ---------------------------------------------------------------------------

_agent: FinAgent | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _agent
    _agent = FinAgent()


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


async def _run_task_background(task_state: TaskState) -> None:
    """Execute the task in the background and persist the updated state."""
    global _agent
    if _agent is None:
        _agent = FinAgent()
    updated = await _agent.run_task(task_state)
    _task_store[updated.task_id] = updated


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Monitoring"])
async def health_check() -> dict[str, Any]:
    """Return service health status and basic statistics."""
    total = len(_task_store)
    by_status: dict[str, int] = {}
    for ts in _task_store.values():
        key = ts.status.value
        by_status[key] = by_status.get(key, 0) + 1
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "total_tasks": total,
        "tasks_by_status": by_status,
        "agent_initialised": _agent is not None,
    }


@app.post("/tasks", response_model=TaskResponse, status_code=202, tags=["Tasks"])
async def submit_task(
    request: TaskRequest,
    background_tasks: BackgroundTasks,
) -> TaskResponse:
    """
    Submit a new task for autonomous execution.

    Returns immediately with a ``task_id`` (HTTP 202 Accepted).
    Poll ``GET /tasks/{task_id}`` to check progress and retrieve the report.
    """
    # Initialise task state
    task_state = TaskState(
        original_task=request.task,
        context=request.context or {},
    )
    _task_store[task_state.task_id] = task_state

    # Schedule background execution
    background_tasks.add_task(_run_task_background, task_state)

    return TaskResponse(
        task_id=task_state.task_id,
        status=task_state.status,
        message="Task accepted. Execution has started in the background.",
    )


@app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
async def get_task(task_id: str) -> TaskResponse:
    """
    Retrieve the current status and result of a task.

    When ``status`` is ``completed``, the ``report`` field contains the
    final evidence-backed report.
    """
    ts = _task_store.get(task_id)
    if ts is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")

    status_messages = {
        TaskStatus.PENDING: "Task is queued and waiting to start.",
        TaskStatus.PLANNING: "Agent is generating the execution plan.",
        TaskStatus.EXECUTING: "Agent is executing the plan.",
        TaskStatus.VERIFYING: "Agent is verifying task completion.",
        TaskStatus.COMPLETED: "Task completed successfully.",
        TaskStatus.FAILED: f"Task failed: {ts.error_message or 'Unknown error.'}",
        TaskStatus.ESCALATED: f"Task escalated to human operator: {ts.error_message or ''}",
    }

    return TaskResponse(
        task_id=ts.task_id,
        status=ts.status,
        message=status_messages.get(ts.status, "Unknown status."),
        report=ts.final_report,
    )


@app.get("/tasks", tags=["Tasks"])
async def list_tasks() -> dict[str, Any]:
    """
    List all tasks with a brief summary (no full reports).
    """
    summary = []
    for ts in _task_store.values():
        summary.append(
            {
                "task_id": ts.task_id,
                "status": ts.status.value,
                "original_task": ts.original_task[:100],
                "step_count": len(ts.steps),
                "retry_count": ts.retry_count,
                "created_at": ts.created_at.isoformat(),
                "completed_at": ts.completed_at.isoformat() if ts.completed_at else None,
            }
        )
    # Most recent first
    summary.sort(key=lambda x: x["created_at"], reverse=True)
    return {"tasks": summary, "total": len(summary)}


@app.delete("/tasks/{task_id}", tags=["Tasks"])
async def delete_task(task_id: str) -> dict[str, str]:
    """Remove a completed or failed task from the in-memory store."""
    if task_id not in _task_store:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    ts = _task_store[task_id]
    if ts.status in (
        TaskStatus.PENDING,
        TaskStatus.PLANNING,
        TaskStatus.EXECUTING,
        TaskStatus.VERIFYING,
    ):
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a task that is still running.",
        )
    del _task_store[task_id]
    return {"message": f"Task '{task_id}' deleted."}


# ---------------------------------------------------------------------------
# Serve Frontend Dashboard
# ---------------------------------------------------------------------------

import os

if os.path.isdir("frontend"):
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
