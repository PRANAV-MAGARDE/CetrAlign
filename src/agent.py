"""
src/agent.py
------------
FinAgent – Core orchestrator for autonomous task execution.

Architecture
~~~~~~~~~~~~
1. PLAN   – Ask the LLM to decompose the task into ordered steps.
2. EXECUTE – Agentic loop: call LLM → dispatch tool calls → feed results back.
3. VERIFY  – Ask the LLM to verify task completion against all steps taken.
4. REPORT  – Generate an evidence-backed final report.

SDK usage
~~~~~~~~~
Uses google-genai SDK v2+ (``from google import genai``):
  - ``genai.Client(api_key=...)``
  - ``client.models.generate_content(model, contents, config)``
  - ``types.Tool(function_declarations=[...])``
  - ``types.GenerateContentConfig(tools=[...], system_instruction=...)``
  - Function-call parts detected via ``part.function_call``
  - Results fed back via ``types.Part.from_function_response(...)``
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any

from google import genai
from google.genai import types
from rich.console import Console
from rich.panel import Panel

from src.config import settings
from src.models import AgentStep, StepType, TaskState, TaskStatus
from src.tools import TOOL_REGISTRY, get_tool_definitions

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

console = Console()

STEP_COLORS: dict[StepType, str] = {
    StepType.PLAN: "cyan",
    StepType.TOOL_CALL: "yellow",
    StepType.OBSERVATION: "green",
    StepType.VERIFICATION: "blue",
    StepType.ESCALATION: "red",
    StepType.RECOVERY: "magenta",
}


def _log(step_type: StepType, msg: str, detail: str = "") -> None:
    color = STEP_COLORS.get(step_type, "white")
    label = f"[{color}][{step_type.value.upper()}][/{color}]"
    if detail:
        console.print(f"{label} {msg}")
        console.print(f"  [dim]{detail}[/dim]")
    else:
        console.print(f"{label} {msg}")


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are FinAgent, an autonomous AI task worker for a Futures & Options (F&O) trading company.

## Your Role
- Execute financial operations with precision and care.
- You have access to internal systems: invoice management, payment processing,
  contract data, open positions, and risk metrics.
- You MUST use the available tools to gather data before drawing conclusions.
- Never fabricate data – always retrieve it from tools first.

## Working with Tools
- Call tools one at a time unless you are certain they are independent.
- After each tool call, analyse the result before deciding the next action.
- If a tool returns an error, attempt to recover (e.g. try a different ID,
  list all records, then pick the correct one).
- When you have gathered enough information to complete the task, respond with
  a clear natural-language answer or confirmation. Do NOT call more tools than necessary.

## Compliance & Risk
- Always verify invoice details before processing a payment.
- Add a compliance note for any payment above INR 100,000 or USD 5,000.
- Escalate if you are uncertain about a financial action that cannot be reversed.
- Log all significant actions to the audit trail.

## Response Style
- Be concise and factual.
- When asked for a report, structure it with sections: Summary, Actions Taken,
  Key Data, Outcome.
- Use Indian financial terminology where appropriate (INR, NSE, SEBI, etc.).
"""

PLAN_PROMPT = """\
You are planning an autonomous task. Break the following task into a numbered
list of concrete, actionable steps. Each step should be specific and measurable.
Output ONLY the numbered list – no preamble, no commentary.

Task: {task}
"""

VERIFY_PROMPT = """\
Review the following task and the execution history below. Determine whether
the task was completed successfully.

Original Task:
{task}

Steps Taken:
{steps_summary}

Respond with either:
- "VERIFIED: <brief explanation>" if the task is fully complete.
- "INCOMPLETE: <what is still missing>" if something was not done.
- "FAILED: <reason>" if the task could not be completed correctly.
"""

REPORT_PROMPT = """\
Generate a professional evidence-backed report for the following completed task.

Original Task:
{task}

Execution Steps:
{steps_summary}

Structure your report with:
1. **Summary** – one-paragraph overview
2. **Actions Taken** – bullet list of concrete actions performed
3. **Key Data** – relevant figures, IDs, amounts extracted
4. **Outcome** – final result and status
5. **Compliance Notes** – any compliance or risk actions taken

Be concise and factual. Use real data from the steps above.
"""


# ---------------------------------------------------------------------------
# FinAgent class
# ---------------------------------------------------------------------------


class FinAgent:
    """Autonomous AI task worker backed by the Gemini LLM."""

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.model
        self._tool_defs = get_tool_definitions()
        console.print(
            Panel(
                f"[bold green]FinAgent initialised[/bold green]\n"
                f"Model : [cyan]{self._model}[/cyan]\n"
                f"Tools : [cyan]{len(self._tool_defs)}[/cyan] registered\n"
                f"Max steps : [cyan]{settings.max_steps}[/cyan]",
                title="FinAgent",
                border_style="green",
            )
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run_task(self, task_state: TaskState) -> TaskState:
        """
        Orchestrate the full lifecycle of *task_state*.

        Returns the updated TaskState with status, steps, and final_report.
        """
        try:
            task_state = await self._plan(task_state)
            task_state = await self._execute(task_state)
            task_state = await self._verify(task_state)
            task_state = await self._report(task_state)
        except Exception as exc:  # pylint: disable=broad-except
            task_state.status = TaskStatus.FAILED
            task_state.error_message = str(exc)
            task_state.completed_at = datetime.utcnow()
            console.print(f"[bold red]Task failed:[/bold red] {exc}")

        return task_state

    # ------------------------------------------------------------------
    # Phase 1: Planning
    # ------------------------------------------------------------------

    async def _plan(self, ts: TaskState) -> TaskState:
        """Ask the LLM to decompose the task into a numbered plan."""
        ts.status = TaskStatus.PLANNING
        _log(StepType.PLAN, f"Planning task: {ts.original_task[:80]}")

        prompt = PLAN_PROMPT.format(task=ts.original_task)
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.2,
                ),
            ),
        )

        raw_plan = response.text or ""
        # Parse numbered list lines
        plan_steps: list[str] = []
        for line in raw_plan.splitlines():
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                # Strip leading "1. " or "- "
                cleaned = line.lstrip("0123456789.-) ").strip()
                if cleaned:
                    plan_steps.append(cleaned)

        ts.plan = plan_steps or [ts.original_task]

        ts.steps.append(
            AgentStep(
                step_type=StepType.PLAN,
                description="Generated execution plan",
                output=ts.plan,
                success=True,
            )
        )
        _log(
            StepType.PLAN,
            f"Plan generated ({len(ts.plan)} steps)",
            "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(ts.plan)),
        )
        return ts

    # ------------------------------------------------------------------
    # Phase 2: Execution (agentic tool-use loop)
    # ------------------------------------------------------------------

    async def _execute(self, ts: TaskState) -> TaskState:
        """
        Run the agentic loop:
          - Build full conversation history
          - Call LLM with tools
          - Dispatch tool calls and feed results back
          - Repeat until LLM signals completion or max_steps reached
        """
        ts.status = TaskStatus.EXECUTING
        _log(StepType.TOOL_CALL, "Starting agentic execution loop")

        # Build Gemini tool object
        tool_obj = types.Tool(function_declarations=self._tool_defs)
        config = types.GenerateContentConfig(
            tools=[tool_obj],
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
        )

        # Conversation history as a list of Content objects
        plan_summary = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(ts.plan or []))
        initial_user_msg = (
            f"Execute the following task:\n\n{ts.original_task}\n\n"
            f"Your execution plan:\n{plan_summary}\n\n"
            "Begin executing the plan now. Use the available tools to complete each step."
        )
        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=initial_user_msg)])
        ]

        step_count = 0

        while step_count < settings.max_steps:
            step_count += 1
            _log(StepType.TOOL_CALL, f"LLM call #{step_count}")

            t0 = time.time()
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                ),
            )
            elapsed_ms = (time.time() - t0) * 1000

            # Append model response to conversation
            if response.candidates and response.candidates[0].content:
                contents.append(response.candidates[0].content)

            # -----------------------------------------------------------
            # Inspect response parts for function calls vs text
            # -----------------------------------------------------------
            function_response_parts: list[types.Part] = []

            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        fc = part.function_call
                        tool_name = fc.name
                        tool_args: dict[str, Any] = dict(fc.args) if fc.args else {}

                        _log(
                            StepType.TOOL_CALL,
                            f"Tool: [bold]{tool_name}[/bold]",
                            f"Args: {json.dumps(tool_args, default=str)[:200]}",
                        )

                        # Dispatch
                        tool_result = await self._call_tool(tool_name, tool_args)

                        duration = (time.time() - t0) * 1000

                        # Record step
                        ts.steps.append(
                            AgentStep(
                                step_type=StepType.TOOL_CALL,
                                description=f"Called tool: {tool_name}",
                                input={"tool": tool_name, "args": tool_args},
                                output=tool_result,
                                success=tool_result.get("success", False),
                                error=tool_result.get("error"),
                                duration_ms=duration,
                            )
                        )

                        # Handle failures / retries
                        if not tool_result.get("success"):
                            ts.retry_count += 1
                            _log(
                                StepType.RECOVERY,
                                f"Tool error (retry {ts.retry_count}): {tool_result.get('error')}",
                            )
                            if ts.retry_count >= settings.human_escalation_threshold:
                                return await self._escalate(
                                    ts, tool_result.get("error", "Unknown error")
                                )

                        # Build function response part
                        function_response_parts.append(
                            types.Part.from_function_response(
                                name=tool_name,
                                response={"result": tool_result},
                            )
                        )

                        _log(
                            StepType.OBSERVATION,
                            f"Tool result: success={tool_result.get('success')}",
                            json.dumps(tool_result.get("data"), default=str)[:300],
                        )

            # Feed all function responses back in one user turn
            if function_response_parts:
                contents.append(types.Content(role="user", parts=function_response_parts))
                continue  # next LLM call

            # No more function calls → model is done
            final_text = response.text or ""
            if final_text.strip():
                _log(StepType.OBSERVATION, "LLM finished execution", final_text[:300])
                ts.steps.append(
                    AgentStep(
                        step_type=StepType.OBSERVATION,
                        description="LLM execution completed",
                        output=final_text,
                        success=True,
                        duration_ms=elapsed_ms,
                    )
                )
                # Store final LLM answer in context for report phase
                ts.context["execution_summary"] = final_text
                break

        else:
            # Exhausted max steps
            ts.steps.append(
                AgentStep(
                    step_type=StepType.ESCALATION,
                    description=f"Max steps ({settings.max_steps}) reached without completion.",
                    success=False,
                )
            )
            ts.status = TaskStatus.ESCALATED
            ts.error_message = f"Task exceeded maximum step limit ({settings.max_steps})."

        return ts

    # ------------------------------------------------------------------
    # Phase 3: Verification
    # ------------------------------------------------------------------

    async def _verify(self, ts: TaskState) -> TaskState:
        """Ask the LLM to verify the task was completed correctly."""
        if ts.status in (TaskStatus.FAILED, TaskStatus.ESCALATED):
            return ts

        ts.status = TaskStatus.VERIFYING
        _log(StepType.VERIFICATION, "Verifying task completion…")

        steps_summary = self._summarise_steps(ts)
        prompt = VERIFY_PROMPT.format(task=ts.original_task, steps_summary=steps_summary)

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.1,
                ),
            ),
        )

        verdict = (response.text or "").strip()
        _log(StepType.VERIFICATION, f"Verdict: {verdict[:120]}")

        success = verdict.upper().startswith("VERIFIED")
        ts.steps.append(
            AgentStep(
                step_type=StepType.VERIFICATION,
                description="LLM verification of task completion",
                output=verdict,
                success=success,
            )
        )

        if not success:
            if verdict.upper().startswith("FAILED"):
                ts.status = TaskStatus.FAILED
                ts.error_message = verdict
            else:
                # INCOMPLETE – mark as failed with message
                ts.status = TaskStatus.FAILED
                ts.error_message = verdict

        return ts

    # ------------------------------------------------------------------
    # Phase 4: Reporting
    # ------------------------------------------------------------------

    async def _report(self, ts: TaskState) -> TaskState:
        """Generate the final evidence-backed report."""
        if ts.status in (TaskStatus.FAILED, TaskStatus.ESCALATED):
            ts.completed_at = datetime.utcnow()
            return ts

        _log(StepType.VERIFICATION, "Generating final report…")

        steps_summary = self._summarise_steps(ts)
        prompt = REPORT_PROMPT.format(task=ts.original_task, steps_summary=steps_summary)

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.2,
                ),
            ),
        )

        ts.final_report = (response.text or "").strip()
        ts.status = TaskStatus.COMPLETED
        ts.completed_at = datetime.utcnow()

        console.print(
            Panel(
                ts.final_report,
                title="[bold green]Final Report[/bold green]",
                border_style="green",
            )
        )
        return ts

    # ------------------------------------------------------------------
    # Escalation
    # ------------------------------------------------------------------

    async def _escalate(self, ts: TaskState, reason: str) -> TaskState:
        """Mark task as escalated and record the reason."""
        ts.status = TaskStatus.ESCALATED
        ts.error_message = f"Escalated to human operator: {reason}"
        ts.completed_at = datetime.utcnow()
        ts.steps.append(
            AgentStep(
                step_type=StepType.ESCALATION,
                description="Task escalated to human operator",
                output={"reason": reason},
                success=False,
                error=reason,
            )
        )
        _log(StepType.ESCALATION, f"[bold red]ESCALATED[/bold red]: {reason}")
        return ts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Look up *tool_name* in the registry and call it with *args*."""
        fn = TOOL_REGISTRY.get(tool_name)
        if fn is None:
            return {"success": False, "data": None, "error": f"Unknown tool: {tool_name!r}"}
        try:
            return await fn(**args)
        except TypeError as exc:
            return {"success": False, "data": None, "error": f"Tool argument error: {exc}"}
        except Exception as exc:  # pylint: disable=broad-except
            return {"success": False, "data": None, "error": str(exc)}

    @staticmethod
    def _summarise_steps(ts: TaskState) -> str:
        """Produce a concise text summary of all steps for LLM prompts."""
        lines: list[str] = []
        for i, step in enumerate(ts.steps, 1):
            status = "[PASS]" if step.success else "[FAIL]"
            lines.append(f"{i}. {status} {step.step_type.value.upper()}: {step.description}")
            if step.output and step.step_type in (StepType.TOOL_CALL, StepType.OBSERVATION):
                snippet = json.dumps(step.output, default=str)[:200]
                lines.append(f"   Output: {snippet}")
            if step.error:
                lines.append(f"   Error: {step.error}")
        return "\n".join(lines)
