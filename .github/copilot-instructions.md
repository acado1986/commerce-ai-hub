# AI Delivery Hub Copilot Instructions

Use `AGENTS.md` as the primary project guide for architecture, workflow stage order, state model, and extension points.

Key rules for this repository:

- This is a LangGraph workflow project with canonical wiring in `src/agent/orchestrator/graph.py`.
- Shared graph state is `src/agent/orchestrator/state.py::DeliveryHubState`.
- Prefer the existing node patterns over adding new abstraction layers.
- Most content-producing stages should be thin wrappers around `generate_markdown(...)` in `src/agent/nodes/generation.py`.
- When changing stage order or adding a stage, update both graph wiring and routing in `src/agent/orchestrator/router.py`.
- Preserve approval-loop behavior, artifact persistence, audit logging, and token usage tracking.
- If a new artifact type is introduced, also check `src/agent/llm.py`, `src/agent/nodes/generation.py`, and `agents/*.md`.

When the task is specifically about creating or changing a LangGraph node or stage, load and follow the `delivery-hub-node-creator` skill from `.github/skills/delivery-hub-node-creator/`.

Preferred verification for workflow changes:

```bash
uv run pytest tests/unit_tests/test_configuration.py tests/unit_tests/test_mcp_graph_driver.py tests/integration_tests/test_graph.py
```
