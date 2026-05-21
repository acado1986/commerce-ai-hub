# Node Patterns

Use this file after reading `AGENTS.md` when you need a quick decision table.

## Pattern Matrix

### Deterministic node

Choose this when the node mainly computes state, validates input, updates routing fields, or writes JSON metadata.

Copy shape from:

- `src/agent/nodes/classify.py`
- `src/agent/nodes/approval.py`
- `src/agent/nodes/audit.py`

Typical edits:

- set `current_stage`
- update `next_action`
- update `artifact_paths`
- append `errors` or `audit_log` when needed

### Single-artifact markdown stage

Choose this when the node creates one markdown document from the request plus prior artifacts.

Copy shape from:

- `src/agent/nodes/requirements.py`
- `src/agent/nodes/architecture.py`
- `src/agent/nodes/qa.py`
- `src/agent/nodes/documentation.py`

Preferred implementation sketch:

```python
from langchain_core.runnables import RunnableConfig

from agent.nodes.generation import generate_markdown
from agent.orchestrator.state import DeliveryHubState


def example_node(
    state: DeliveryHubState,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    return generate_markdown(
        state=state,
        stage="example",
        artifact_name="example.md",
        agent_profile="documentation_agent.md",
        context_artifacts=["requirements.md"],
        config=config,
        instruction="Create the requested artifact.",
    )
```

### Multi-artifact stage

Choose this when a stage emits two related artifacts.

Copy shape from:

- `src/agent/nodes/planning.py`

Rule:

- keep the first artifact generation result in `state`
- pass that updated state into the second `generate_markdown(...)` call

### Router-only change

Choose this when the request changes graph transitions without changing node internals.

Files to inspect:

- `src/agent/orchestrator/graph.py`
- `src/agent/orchestrator/router.py`

Minimum check:

- stage can be reached
- stage can be resumed after approval
- terminal path still ends at `audit` or `END` intentionally

### Approval-loop change

Choose this when a stage should pause for review, revise in place, or skip approval.

Files to inspect:

- `src/agent/nodes/approval.py`
- `src/agent/nodes/approval_router.py`
- `src/agent/orchestrator/router.py`
- `src/agent/chat_graph.py`

Warning:

- approval behavior is cross-cutting; do not change it in only one file

## New Stage Checklist

1. Add the node file.
2. Wire it into `src/agent/orchestrator/graph.py`.
3. Update forward routing in `src/agent/orchestrator/router.py`.
4. Update approval resume routing in `route_after_approval(...)`.
5. Update artifact/profile/deployment mappings if the stage adds a new artifact.
6. Update tests.
