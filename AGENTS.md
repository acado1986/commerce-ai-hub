# AI Delivery Hub

## What This Repo Is

This project is a LangGraph-based delivery workflow for turning a human request into staged delivery artifacts with approval gates, audit logs, and optional MCP/chat entrypoints.

Primary entrypoints:

- `src/agent/graph.py`: exported studio graph.
- `src/agent/chat_graph.py`: chat wrapper around the workflow graph.
- `src/agent/orchestrator/graph.py`: canonical graph builder and stage wiring.
- `src/agent/mcp_server.py`: MCP tools that drive the graph incrementally.

The current default stage order is:

`START -> intake -> classify -> requirements -> architecture -> planning -> qa -> documentation -> audit -> END`

Human approval is interleaved through `approval` and `approval_router`. Most content-producing stages stop with `next_action="human_review"` and only continue after approval or revision.

## Shared State

The graph uses a single shared typed dict: `src/agent/orchestrator/state.py::DeliveryHubState`.

Fields that matter most when editing the workflow:

- `input_text`: original user request.
- `request_type`, `mapped_request_type`, `platforms`, `risk_level`: classification outputs.
- `current_stage`: latest completed node.
- `approval_status`, `approval_stage`, `revision_stage`, `revision_instruction`: approval loop control.
- `next_action`: routing flag such as `continue`, `human_review`, or `revise`.
- `artifact_paths`: artifact name to filesystem path map.
- `audit_log`, `llm_usage`, `llm_usage_totals`, `errors`: observability and failure tracking.

Prefer extending existing state keys only when they represent durable workflow state. Avoid adding transient prompt-only values unless the graph actually needs to route or resume on them.

## Existing Node Patterns

### 1. Deterministic state/update nodes

Use this pattern when a node mostly parses input, normalizes data, writes a small JSON artifact, or updates routing fields.

Examples:

- `src/agent/nodes/intake.py`
- `src/agent/nodes/classify.py`
- `src/agent/nodes/audit.py`
- `src/agent/nodes/approval.py`
- `src/agent/nodes/approval_router.py`

Characteristics:

- direct Python logic
- optional artifact write through `src/agent/nodes/common.py`
- returns a partial `DeliveryHubState`
- may set `next_action` for downstream routing

### 2. LLM artifact-generation nodes

Use this pattern when a stage produces markdown artifacts from the shared workflow context.

Examples:

- `src/agent/nodes/requirements.py`
- `src/agent/nodes/architecture.py`
- `src/agent/nodes/planning.py`
- `src/agent/nodes/qa.py`
- `src/agent/nodes/documentation.py`

Preferred implementation:

- wrap `generate_markdown(...)` from `src/agent/nodes/generation.py`
- pass `stage`, `artifact_name`, `agent_profile`, `context_artifacts`, and a tight `instruction`

What `generate_markdown(...)` already handles:

- model selection
- agent-profile prompt context
- artifact reads from prior stages
- revision requests
- artifact persistence
- audit and token usage tracking
- setting `approval_status="pending"` and `next_action="human_review"`

If a stage needs multiple artifacts, chain multiple `generate_markdown(...)` calls in the same node like `planning_node`.

### 3. Routing helpers

Routing lives in `src/agent/orchestrator/router.py`.

Update it when:

- a new stage is inserted
- stage order changes
- approval resume behavior changes
- request-type-to-workflow mapping changes

### 4. Graph composition

Canonical workflow wiring lives in `src/agent/orchestrator/graph.py`.

Update it when:

- adding a node to the main workflow
- changing stage order
- inserting approval behavior around a new stage

If the chat UX also needs to understand the new stage, review `src/agent/chat_graph.py`.

## Artifact And Agent Conventions

Artifact-producing stages are role-driven:

- agent profiles live in `agents/*.md`
- `src/agent/agent_runtime.py` loads them into prompt context
- `src/agent/nodes/generation.py::DEFAULT_AGENT_BY_ARTIFACT` maps common artifact names to profile files

If you add a new artifact type, check whether you also need:

- a new agent profile in `agents/`
- a deployment rule in `src/agent/llm.py::deployment_for_artifact`
- a default profile mapping in `src/agent/nodes/generation.py`

Artifacts are written under `artifacts/runs/<run_id>/`.

## How To Add A New Stage

When adding a new stage, usually touch these files:

1. Create `src/agent/nodes/<stage>.py`.
2. Export it from `src/agent/nodes/__init__.py` if needed.
3. Wire it in `src/agent/orchestrator/graph.py`.
4. Update `src/agent/orchestrator/router.py`.
5. If it produces a new artifact, update:
   - `src/agent/nodes/generation.py`
   - `src/agent/llm.py`
   - `agents/<profile>.md` if a new role is needed
6. If chat/MCP behavior depends on the new stage, review:
   - `src/agent/chat_graph.py`
   - `src/agent/mcp_server.py`
7. Add or update tests.

Use the smallest viable change. Most new content stages should be thin wrappers around `generate_markdown(...)`, not bespoke mini-frameworks.

## Testing Expectations

Relevant tests:

- `tests/unit_tests/test_configuration.py`: routing and deployment rules
- `tests/unit_tests/test_mcp_graph_driver.py`: checkpoint/MCP flow
- `tests/integration_tests/test_graph.py`: end-to-end artifact creation

Useful commands:

```bash
uv run pytest tests/unit_tests/test_configuration.py tests/unit_tests/test_mcp_graph_driver.py tests/integration_tests/test_graph.py
```

For broader verification:

```bash
uv run pytest
```

## Working Rules For AI Agents

- Preserve the shared-state model; do not invent parallel state systems.
- Prefer existing helpers before adding abstractions.
- Keep stage nodes small and explicit.
- Keep approval semantics intact unless the task is specifically about approval flow.
- Do not bypass audit, artifact persistence, or LLM usage tracking for content-producing stages.
- When changing stage order, update both forward routing and approval resume routing.
