<<<<<<< HEAD
# FinAgent — Autonomous AI Task Worker for F&O Finance

FinAgent is a production-grade autonomous AI agent designed to handle end-to-end operational workflows in Futures & Options (F&O) finance. Given a natural-language instruction, FinAgent plans a sequence of sub-steps, executes specialized financial tools, verifies outcomes, and produces an evidence-backed audit report — all without human intervention. It supports adaptive retry logic and human escalation when tasks cannot be resolved automatically.

---

## Architecture Diagram

```
User (NL Task)
      │
      ▼
 ┌─────────────────────────────────────────────┐
 │              FinAgent Orchestrator           │
 │                                             │
 │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
 │  │  Planner │→ │ Executor │→ │ Verifier │  │
 │  └──────────┘  └──────────┘  └──────────┘  │
 │        │            │              │        │
 │        └────────────┴──────────────┘        │
 │                     │                       │
 │             State Tracker                   │
 │        (TaskState, AgentStep log)           │
 │                     │                       │
 │         ┌───────────┴──────────┐            │
 │         │   Adaptive Recovery  │            │
 │         │  Human Escalation    │            │
 │         └──────────────────────┘            │
 └─────────────────────────────────────────────┘
             │                  │
    ┌─────────────────┐  ┌─────────────────┐
    │  Gemini 3.8     │  │  Tool Registry  │
    │  Flash LLM      │  │  (10 F&O tools) │
    └─────────────────┘  └─────────────────┘
                                │
              ┌─────────────────────────────┐
              │   Simulated F&O Database    │
              │  Contracts, Invoices,       │
              │  Positions, Audit Log       │
              └─────────────────────────────┘
```

---

## Setup & Run

### Prerequisites
- Python 3.11+
- A valid `GEMINI_API_KEY` from [Google AI Studio](https://aistudio.google.com/)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-org/finagent.git
cd finagent

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
.venv\Scripts\activate          # Windows

# 3. Install dependencies
pip install -e .
```

### Configuration

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.0-flash
MAX_AGENT_STEPS=20
LOG_LEVEL=INFO
```

### Run the CLI

```bash
python main.py
```

### Run the API Server

```bash
uvicorn api:app --reload --port 8000
```

### Run the Demo

```bash
python demo/run_demo.py
```

---

## CLI Examples

Once `python main.py` is running, you will be prompted for a task. Here are three sample inputs:

### Task 1 — Invoice Payment Workflow
```
Enter task: Find the latest invoice from Zerodha Clearing, extract the amount and due date, process the payment, and confirm completion.
```

Expected output:
```
[Planner]   Step 1: search_invoices(vendor="Zerodha Clearing")
[Planner]   Step 2: get_invoice_details(invoice_id=<result>)
[Planner]   Step 3: process_payment(invoice_id=<result>, amount=<result>)
[Planner]   Step 4: verify_payment_status(payment_id=<result>)
[Executor]  ... executing steps ...
[Verifier]  ✅ Task completed. Payment INV-2026-001 processed. Amount: ₹4,85,000. Status: CONFIRMED.
```

### Task 2 — Risk Metrics Check
```
Enter task: Get the current risk metrics for our portfolio and identify if we are over the margin limit.
```

Expected output:
```
[Planner]   Step 1: get_risk_metrics()
[Planner]   Step 2: get_all_positions()
[Executor]  ... executing steps ...
[Verifier]  ✅ Portfolio utilization: 73.2%. Margin available: ₹26,80,000. No breach detected.
```

### Task 3 — Contract + Margin Query
```
Enter task: Check the details of the NIFTY50 futures contract expiring in October 2026 and calculate margin required for 5 lots.
```

Expected output:
```
[Planner]   Step 1: get_contract_details(symbol="NIFTY50", contract_type="FUTURE", expiry="OCT-2026")
[Planner]   Step 2: check_margin_requirements(contract_id=<result>, lots=5)
[Executor]  ... executing steps ...
[Verifier]  ✅ NIFTY50 OCT-2026 FUT: Lot size 50, LTP ₹24,850. Margin for 5 lots: ₹12,42,500.
```

---

## API Examples

The REST API is available at `http://localhost:8000` after starting the server.

### Submit a Task

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Show me all pending invoices and their total amount due.",
    "max_steps": 15
  }'
```

Response:
```json
{
  "task_id": "task_abc123",
  "status": "PENDING",
  "message": "Task queued for execution"
}
```

### Get Task Status

```bash
curl http://localhost:8000/tasks/task_abc123
```

Response:
```json
{
  "task_id": "task_abc123",
  "status": "COMPLETED",
  "result": "Found 3 pending invoices. Total due: ₹12,35,000.",
  "steps_taken": 2,
  "execution_time_seconds": 4.2,
  "steps": [
    {
      "step_number": 1,
      "tool": "get_pending_invoices",
      "input": {},
      "output": { "invoices": ["INV-2026-002", "INV-2026-003", "INV-2026-005"] },
      "timestamp": "2026-10-08T12:00:01Z"
    }
  ]
}
```

### List All Tasks

```bash
curl http://localhost:8000/tasks
```

### Get Audit Log

```bash
curl http://localhost:8000/audit
```

### API Docs (auto-generated)

```
http://localhost:8000/docs       # Swagger UI
http://localhost:8000/redoc      # ReDoc
```

---

## Architecture Explanation

FinAgent implements a **Plan → Execute → Verify** agentic loop with 9 core capabilities:

### 1. Goal Understanding
The Gemini 3.8 Flash LLM receives the raw natural-language task and parses it into a structured intent object — identifying the primary goal, entities mentioned (vendors, contracts, invoice IDs), and the class of operation (query, payment, compliance).

### 2. Planning
Before touching any tool, FinAgent generates a complete ordered list of sub-steps. The planner prompt includes the full tool schema so Gemini can reason about which tools are available and in what sequence they must be called. Planning is separated from execution intentionally — this prevents the agent from "rushing" into tool calls without a coherent strategy.

### 3. Tool Execution
A registry of **10 specialized F&O tools** handles all side effects:
| Tool | Purpose |
|---|---|
| `search_invoices` | Search invoices by vendor, date, or status |
| `get_invoice_details` | Retrieve full invoice metadata |
| `get_pending_invoices` | List all unpaid invoices |
| `process_payment` | Submit payment for an invoice |
| `verify_payment_status` | Confirm payment settlement |
| `get_contract_details` | Fetch F&O contract specifications |
| `check_margin_requirements` | Calculate SPAN/exposure margin |
| `get_risk_metrics` | Portfolio VaR, utilization, drawdown |
| `get_all_positions` | Current open positions with PnL |
| `add_compliance_note` | Attach audit note to a payment record |

### 4. Observation
Each tool call produces an `AgentStep` — a structured record containing the tool name, input parameters, raw output, any error, and an ISO 8601 timestamp. Observations are fed back into the LLM context for subsequent steps, enabling data to flow through a multi-step workflow (e.g., using an `invoice_id` returned in step 1 as input to step 2).

### 5. State Tracking
A `TaskState` Pydantic model holds the complete execution history: task ID, original instruction, all `AgentStep` records, current status, retry count, and the final result. This state object is the single source of truth for reporting, debugging, and audit.

### 6. Adaptive Recovery
When a tool returns an error, FinAgent does not immediately fail. It applies exponential backoff (1s, 2s, 4s...) and re-invokes the planner with the error context appended. The LLM can then revise its approach — for example, trying a different search query or splitting a payment into smaller chunks. After `N` retries (configurable), the task is escalated.

### 7. Outcome Verification
After execution, a separate **Verifier** prompt asks the LLM: *"Was the original task fully completed? What evidence do you have?"* This catches partial completions (e.g., payment initiated but not confirmed) and can trigger additional tool calls if needed.

### 8. Human Escalation
If the agent exhausts its retry budget or the verifier determines the task is unresolvable, the `TaskState.status` is set to `NEEDS_HUMAN_REVIEW` and the full step log is preserved. An operator can inspect the audit trail and decide the next action.

### 9. Evidence-backed Reporting
The final report is not a hallucinated summary — it cites every tool call and result by name, including amounts, IDs, and timestamps drawn from actual `AgentStep` outputs. This makes the output auditable and trustworthy for finance teams.

---

## Technical & Design Decisions

### Why Gemini 3.8 Flash?
Gemini 3.8 Flash offers the optimal balance for this use case: a 1M-token context window (critical for accumulating long step histories), native function-calling support (no prompt engineering hacks needed), fast inference (~1–2s per call), and strong reasoning capability for multi-step financial workflows. The cost-per-token is also well-suited for agentic loops that may issue 10–20 LLM calls per task.

### Why a Simulated Database Instead of a Real One?
The simulated F&O database demonstrates the tool-use and agentic patterns without requiring brokerage API keys, clearing house connectivity, or exchange infrastructure. Any real system would swap the simulated tool implementations for real API clients — the agent architecture is identical. This makes the project fully runnable from a laptop with only a Gemini API key.

### Why FastAPI?
FastAPI is async-native (built on Starlette/asyncio), which is essential for an agent server that may be waiting on multiple LLM calls and tool executions concurrently. It generates OpenAPI documentation automatically and is production-ready out of the box with Uvicorn.

### Why Pydantic Models?
`TaskState`, `AgentStep`, and `TaskRequest` are all Pydantic v2 models. This provides strict type validation at runtime, clean JSON serialization for the API, and self-documenting state contracts. When something goes wrong, the traceback pinpoints the exact field and type that failed — invaluable in complex agentic state machines.

### Why an Agentic Loop with a Max-Step Budget?
Without a ceiling on iterations, a misguided planner could issue LLM calls indefinitely. The `MAX_AGENT_STEPS` budget (default: 20) ensures the agent terminates even in pathological cases. It also provides a natural cost-control mechanism for production deployments.

### Separation of Planning and Execution Phases
Research (ReAct, OpenAI function-calling benchmarks) consistently shows that agents perform better when they plan first and execute second, rather than interleaving planning with tool calls. The dedicated planning phase also makes the agent's reasoning transparent — you can log and inspect the full plan before a single tool is called.

---

## Known Limitations

- **Simulated database only** — No real brokerage API integration (Zerodha, IBKR, NSE clearing).
- **No persistent storage** — All task state is in-memory and resets when the server restarts.
- **Single-agent architecture** — No multi-agent coordination (e.g., a separate Auditor agent running in parallel).
- **No real-time market data** — Contract prices and margin rates are static fixtures in the simulated DB.
- **Human escalation is passive** — The system flags tasks for human review but does not send Slack/email notifications.
- **No authentication on API endpoints** — All endpoints are open; not suitable for production without an auth layer.
- **English only** — The planner prompt and tool descriptions are in English; multilingual tasks are unsupported.

---

## What Would Be Built Next

| Priority | Feature | Notes |
|---|---|---|
| 🔴 High | **Real brokerage API integration** | Zerodha Kite Connect, IBKR TWS API |
| 🔴 High | **Persistent PostgreSQL storage** | SQLAlchemy ORM, Alembic migrations |
| 🟠 Medium | **Multi-agent architecture** | Separate Planner, Executor, Auditor agents with message passing |
| 🟠 Medium | **Slack/email escalation notifications** | Webhooks triggered on `NEEDS_HUMAN_REVIEW` status |
| 🟠 Medium | **Web UI dashboard** | React frontend for real-time task monitoring and audit trail |
| 🟡 Low | **Fine-tuned domain model** | Fine-tune Gemini on F&O terminology, SEBI regulations, clearing house formats |
| 🟡 Low | **Vector DB institutional memory** | Store past task outcomes; agent learns from prior successes/failures |
| 🟡 Low | **Real-time market data** | WebSocket feed for live LTP, IV, and margin updates |

---

## Assumptions

- All user tasks are written in English.
- The company operates in Indian markets and handles NSE-listed F&O contracts (NIFTY, BANKNIFTY, stock derivatives).
- Invoices are issued by brokers, clearing houses (NSE Clearing Corp, ICCL), or financial data vendors.
- Payments under **INR 10 lakhs** can be auto-approved by the agent without additional human sign-off.
- A valid `GEMINI_API_KEY` is available in the environment at runtime.
- The simulated database reflects a realistic but fictional institutional portfolio for demonstration purposes.

---

## Models, APIs & Frameworks Used

| Component | Technology | Version | Purpose |
|---|---|---|---|
| LLM | Google Gemini 3.8 Flash (`gemini-2.0-flash`) | via `google-genai >= 2.25.0` | Planning, reasoning, verification |
| API Server | FastAPI | `>= 0.111.0` | REST API for task submission and monitoring |
| Data Validation | Pydantic v2 | `>= 2.7.0` | State modeling, request/response schemas |
| Settings | pydantic-settings | `>= 2.3.0` | Environment variable management |
| Terminal UI | Rich | `>= 13.7.0` | Colored output, tables, progress bars |
| ASGI Server | Uvicorn | `>= 0.30.0` | Production-grade async HTTP server |
| HTTP Client | HTTPX | `>= 0.27.0` | Async HTTP for tool integrations |
| Async File I/O | aiofiles | `>= 23.2.1` | Non-blocking file operations |
| Runtime | Python | `>= 3.11` | Language runtime |

---

## License

MIT License. See [LICENSE](LICENSE) for details.

