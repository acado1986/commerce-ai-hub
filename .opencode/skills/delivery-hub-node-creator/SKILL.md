---
name: delivery-hub-node-creator
description: "Use when asked to add, update, remove, or rewire a LangGraph node or stage in this AI Delivery Hub repository. Inspect what the requested node needs to do, then choose the correct implementation pattern: deterministic state node, LLM artifact-generation node, multi-artifact stage, routing change, approval-flow change, or chat/MCP wrapper update. Follow the repo's existing LangGraph structure instead of inventing a new abstraction."
---

# Delivery Hub Node Creator

## Quick Start

1. Read `AGENTS.md`.
2. Inspect the nearest existing node with the same shape before editing.

Useful starting points:

- graph wiring: `src/agent/orchestrator/graph.py`
- routing: `src/agent/orchestrator/router.py`
- shared state: `src/agent/orchestrator/state.py`
- generic content stage helper: `src/agent/nodes/generation.py`
- thin content stages: `src/agent/nodes/requirements.py`, `architecture.py`, `qa.py`, `documentation.py`
- deterministic nodes: `src/agent/nodes/classify.py`, `approval.py`, `audit.py`

## Decide The Node Type First

### Use a deterministic node when the request is about:

- parsing or normalizing input
- setting workflow flags
- writing JSON metadata
- computing routing state
- approval or revision control
- filesystem logic that does not require LLM drafting

Implementation rule:

- write explicit Python in `src/agent/nodes/<name>.py`
- return a partial `DeliveryHubState`
- use helpers from `src/agent/nodes/common.py` for artifact writes

### Use an LLM artifact-generation node when the request is about:

- generating markdown from the request and prior artifacts
- producing a new delivery document
- revising a document during the approval loop

Implementation rule:

- prefer a thin wrapper around `generate_markdown(...)`
- keep the custom logic limited to `artifact_name`, `agent_profile`, `context_artifacts`, and `instruction`

### Use a multi-artifact stage when the request is about:

- one stage producing more than one artifact
- a second artifact that depends on the first artifact from the same stage

Implementation rule:

- chain `generate_markdown(...)` calls in the node
- keep the same `stage` name across those calls unless the workflow truly needs separate stages

### Use routing changes when the request is about:

- inserting or skipping stages
- changing stage order
- routing after approval
- mapping request types to workflows

Implementation rule:

- update `src/agent/orchestrator/router.py`
- update `src/agent/orchestrator/graph.py`
- keep forward routing and resume-from-approval routing consistent

### Update chat or MCP wrappers only when the request affects:

- chat approval prompts
- chat completion formatting
- MCP staged execution behavior
- persisted run status surfaced to clients

Implementation targets:

- `src/agent/chat_graph.py`
- `src/agent/mcp_server.py`

## Required File Touches By Scenario

When adding a new stage, usually update:

- `src/agent/nodes/<stage>.py`
- `src/agent/orchestrator/graph.py`
- `src/agent/orchestrator/router.py`

Also update these when applicable:

- new artifact file or profile mapping:
  - `src/agent/nodes/generation.py`
  - `src/agent/llm.py`
  - `agents/<profile>.md`
- chat-visible stage behavior:
  - `src/agent/chat_graph.py`
- MCP-visible stage behavior:
  - `src/agent/mcp_server.py`
- tests:
  - `tests/unit_tests/test_configuration.py`
  - `tests/unit_tests/test_mcp_graph_driver.py`
  - `tests/integration_tests/test_graph.py`

## Implementation Rules

- Match the repo's existing style: small node files, explicit routing, shared helper usage.
- Prefer adding a focused node over adding a generic framework layer.
- Do not bypass `generate_markdown(...)` for markdown-producing stages unless the task requires a different model interaction pattern.
- Keep `current_stage`, `approval_stage`, `approval_status`, and `next_action` coherent.
- If the stage produces artifacts, preserve audit and token tracking.
- If the change introduces a new artifact name, update deployment/profile mapping where needed.
- If the change affects approval sequencing, verify `route_after_approval(...)`.

## Validation

Run the smallest relevant test set first:

```bash
uv run pytest tests/unit_tests/test_configuration.py tests/unit_tests/test_mcp_graph_driver.py tests/integration_tests/test_graph.py
```
