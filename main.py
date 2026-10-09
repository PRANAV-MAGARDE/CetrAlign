"""
main.py
-------
FinAgent entry point.

Modes
~~~~~
Server mode (default):
    python main.py
    → Loads .env, starts uvicorn on 0.0.0.0:8000

CLI mode:
    python main.py --task "Pay all pending Zerodha invoices"
    → Runs the agent directly in the terminal, printing rich output

Optional flags:
    --host HOST         Bind host (default: 0.0.0.0)
    --port PORT         Bind port (default: 8000)
    --reload            Enable uvicorn auto-reload (dev mode)
    --task TASK         Run a single task in CLI mode then exit
    --log-level LEVEL   Override log level (DEBUG/INFO/WARNING/ERROR)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# ---------------------------------------------------------------------------
# Load .env before importing anything that reads settings
# ---------------------------------------------------------------------------


def _load_dotenv() -> None:
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv  # type: ignore[import]

        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
        else:
            load_dotenv(override=False)  # searches CWD and parents
    except ImportError:
        pass  # python-dotenv not installed; rely on real env vars


_load_dotenv()

# ---------------------------------------------------------------------------
# Init console
# ---------------------------------------------------------------------------

console = Console()

# ---------------------------------------------------------------------------
# CLI mode helpers
# ---------------------------------------------------------------------------


async def _run_cli_task(task_description: str) -> int:
    """
    Execute a single task in CLI mode using the FinAgent directly.

    Returns 0 on success, 1 on failure/escalation.
    """
    from src.agent import FinAgent
    from src.models import TaskState, TaskStatus

    console.print(
        Panel(
            f"[bold cyan]Task:[/bold cyan] {task_description}",
            title="[bold]FinAgent CLI[/bold]",
            border_style="cyan",
        )
    )

    agent = FinAgent()
    task_state = TaskState(original_task=task_description)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task("Running agent…", total=None)
        task_state = await agent.run_task(task_state)

    # Print outcome
    if task_state.status == TaskStatus.COMPLETED:
        console.print(
            Panel(
                f"[green]Status:[/green] {task_state.status.value.upper()}\n\n"
                + (task_state.final_report or ""),
                title="[bold green]Task Completed[/bold green]",
                border_style="green",
            )
        )
        return 0

    elif task_state.status == TaskStatus.ESCALATED:
        console.print(
            Panel(
                f"[yellow]Status:[/yellow] ESCALATED\n\n"
                f"Reason: {task_state.error_message or 'Unknown'}",
                title="[bold yellow]Task Escalated[/bold yellow]",
                border_style="yellow",
            )
        )
        return 1

    else:
        console.print(
            Panel(
                f"[red]Status:[/red] {task_state.status.value.upper()}\n\n"
                f"Error: {task_state.error_message or 'Unknown error'}",
                title="[bold red]Task Failed[/bold red]",
                border_style="red",
            )
        )
        return 1


# ---------------------------------------------------------------------------
# Server mode
# ---------------------------------------------------------------------------


def _run_server(host: str, port: int, reload: bool, log_level: str) -> None:
    """Start the uvicorn server serving the FastAPI application."""
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    console.print(
        Panel(
            f"[bold green]FinAgent API Server[/bold green]\n"
            f"Host  : [cyan]http://{display_host}:{port}[/cyan]\n"
            f"Docs  : [cyan]http://{display_host}:{port}/docs[/cyan]\n"
            f"Health: [cyan]http://{display_host}:{port}/health[/cyan]\n"
            f"Reload: [cyan]{reload}[/cyan]",
            border_style="green",
        )
    )
    uvicorn.run(
        "src.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level.lower(),
    )


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finagent",
        description="FinAgent – Autonomous AI Task Worker for F&O Finance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py                          # Start API server\n"
            "  python main.py --task 'List pending invoices'\n"
            "  python main.py --port 9000 --reload     # Dev server on port 9000\n"
        ),
    )

    # CLI task mode
    parser.add_argument(
        "--task",
        metavar="TASK",
        type=str,
        default=None,
        help="Run a single agent task in CLI mode and exit.",
    )

    # Server options
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Bind host for the API server (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port for the API server (default: 8000).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable uvicorn auto-reload (development mode).",
    )
    parser.add_argument(
        "--log-level",
        metavar="LEVEL",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Log level (default: info).",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Validate API key before doing anything useful
    from src.config import settings

    if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_api_key_here":
        console.print(
            "[bold red]Error:[/bold red] GEMINI_API_KEY is not set.\n"
            "Copy [cyan].env.example[/cyan] to [cyan].env[/cyan] and add your key, "
            "or set the environment variable directly."
        )
        sys.exit(1)

    if args.task:
        # CLI mode
        exit_code = asyncio.run(_run_cli_task(args.task))
        sys.exit(exit_code)
    else:
        # Server mode
        _run_server(
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level,
        )


if __name__ == "__main__":
    main()
