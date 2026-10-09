"""
FinAgent Demo Runner
====================
Runs 3 representative sample tasks through the FinAgent system and prints
a rich summary table. Requires a valid GEMINI_API_KEY in .env or the shell
environment.

Usage:
    python demo/run_demo.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so we can import from src/
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env before importing anything that reads environment variables
from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from rich import box  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.text import Text  # noqa: E402

# ---------------------------------------------------------------------------
# Project imports — these will fail with a helpful message if not found
# ---------------------------------------------------------------------------
try:
    from src.agent import FinAgent  # type: ignore[import]
    from src.models import TaskRequest, TaskState  # type: ignore[import]
except ImportError as exc:
    Console().print(
        f"[bold red]Import error:[/] {exc}\n"
        "Make sure you ran [cyan]pip install -e .[/] from the project root.",
        highlight=False,
    )
    sys.exit(1)

console = Console()

# ---------------------------------------------------------------------------
# Load sample tasks
# ---------------------------------------------------------------------------
SAMPLE_TASKS_PATH = Path(__file__).parent / "sample_tasks.json"

with SAMPLE_TASKS_PATH.open() as f:
    ALL_TASKS: list[dict] = json.load(f)

# We run tasks with ids 1, 3, and 4
DEMO_TASK_IDS = {1, 3, 4}
DEMO_TASKS = [t for t in ALL_TASKS if t["id"] in DEMO_TASK_IDS]


# ---------------------------------------------------------------------------
# Helper: pretty-print a completed TaskState
# ---------------------------------------------------------------------------
def print_task_result(task_meta: dict, state: TaskState, elapsed: float) -> None:
    status_color = {
        "COMPLETED": "green",
        "NEEDS_HUMAN_REVIEW": "yellow",
        "FAILED": "red",
    }.get(state.status, "white")

    console.print()
    console.print(
        Panel(
            f"[bold]Task #{task_meta['id']}[/] — [italic]{task_meta['category']}[/]\n\n"
            f"[dim]{task_meta['task']}[/]\n\n"
            f"Status : [{status_color}]{state.status}[/{status_color}]\n"
            f"Steps  : {len(state.steps)}\n"
            f"Time   : {elapsed:.2f}s\n\n"
            f"[bold]Result:[/]\n{state.result or '—'}",
            title=f"[cyan]FinAgent[/] Task #{task_meta['id']}",
            border_style=status_color,
            expand=False,
        )
    )

    if state.steps:
        step_table = Table(
            "Step",
            "Tool",
            "Status",
            "Timestamp",
            box=box.SIMPLE_HEAVY,
            show_header=True,
            header_style="bold magenta",
        )
        for step in state.steps:
            step_ok = "✅" if not step.error else "❌"
            step_table.add_row(
                str(step.step_number),
                step.tool_name,
                step_ok,
                step.timestamp.strftime("%H:%M:%S") if step.timestamp else "—",
            )
        console.print(step_table)


# ---------------------------------------------------------------------------
# Main demo runner
# ---------------------------------------------------------------------------
def main() -> None:
    # ── Header ──────────────────────────────────────────────────────────────
    header = Text("FinAgent", style="bold cyan")
    header.append(" — Autonomous AI Task Worker for F&O Finance", style="bold white")
    console.print()
    console.print(Panel(header, subtitle="[dim]Demo Run[/]", border_style="cyan"))
    console.print(
        f"\nRunning [bold]{len(DEMO_TASKS)}[/] sample tasks "
        f"(IDs: {', '.join(str(t['id']) for t in DEMO_TASKS)})\n",
        highlight=False,
    )

    agent = FinAgent()

    summary_rows: list[tuple[str, str, str, str, str]] = []

    for task_meta in DEMO_TASKS:
        task_label = f"Task #{task_meta['id']}: {task_meta['task'][:60]}..."
        console.rule(f"[bold blue]{task_label}[/]")

        request = TaskRequest(task=task_meta["task"])

        # ── Run with a spinner ───────────────────────────────────────────────
        start = time.perf_counter()
        state: TaskState | None = None
        error_msg: str | None = None

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            progress_task = progress.add_task(
                f"[cyan]Executing task #{task_meta['id']}…", total=None
            )
            try:
                state = agent.run(request)
            except Exception as exc:  # noqa: BLE001
                error_msg = str(exc)
            finally:
                progress.update(progress_task, completed=True)

        elapsed = time.perf_counter() - start

        # ── Display result ───────────────────────────────────────────────────
        if state is not None:
            print_task_result(task_meta, state, elapsed)
            summary_rows.append(
                (
                    str(task_meta["id"]),
                    task_meta["category"],
                    state.status,
                    str(len(state.steps)),
                    f"{elapsed:.2f}s",
                )
            )
        else:
            console.print(f"[bold red]ERROR:[/] {error_msg}")
            summary_rows.append(
                (
                    str(task_meta["id"]),
                    task_meta["category"],
                    "ERROR",
                    "—",
                    f"{elapsed:.2f}s",
                )
            )

    # ── Final Summary Table ──────────────────────────────────────────────────
    console.print()
    console.rule("[bold green]Demo Complete — Summary[/]")
    console.print()

    summary_table = Table(
        "Task ID",
        "Category",
        "Status",
        "Steps Taken",
        "Time",
        box=box.DOUBLE_EDGE,
        show_header=True,
        header_style="bold white on dark_blue",
        title="[bold cyan]FinAgent Demo Summary[/]",
        title_style="bold",
    )

    status_styles = {
        "COMPLETED": "green",
        "NEEDS_HUMAN_REVIEW": "yellow",
        "FAILED": "red",
        "ERROR": "bold red",
    }

    for row in summary_rows:
        task_id, category, status, steps, elapsed = row
        style = status_styles.get(status, "white")
        summary_table.add_row(
            task_id,
            category,
            f"[{style}]{status}[/{style}]",
            steps,
            elapsed,
        )

    console.print(summary_table)
    console.print()

    completed = sum(1 for r in summary_rows if r[2] == "COMPLETED")
    console.print(
        f"[bold green]{completed}[/] / [bold]{len(summary_rows)}[/] tasks completed successfully.\n"
    )


if __name__ == "__main__":
    main()
