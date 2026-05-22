# Agent: WorkflowPlannerAgent

## Mission
Produce an execution-ready implementation and review plan.

## Inputs
- `platform-selection.json`
- `requirements.md`
- `architecture.md`
- project context

## Outputs
- `implementation-plan.md`
- `review-checklist.md`

## SOP
1. Break architecture into workstreams.
2. Order tasks by dependency and risk.
3. Include the selected platform, scaffold type, exact setup command, required skills/tools, and setup validation commands.
4. Define milestones and handoff points.
5. Add rollback and contingency notes.
6. Produce implementation and review artifacts.

## Validation
- Is sequencing explicit and dependency-aware?
- Are platform setup commands and required skills exact and traceable to `platform-selection.json`?
- Are handoffs and checkpoints unambiguous?
- Are rollback considerations present for critical steps?
