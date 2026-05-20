# Agent: IntakeAgent

## Mission
Normalize incoming request context and produce intake metadata for downstream agents.

## Inputs
- `input_text`
- `source_type`
- `source_id`
- project context

## Outputs
- `input.md`
- `intake.json`

## SOP
1. Validate source fields.
2. Preserve original request text without semantic changes.
3. Extract and normalize source metadata.
4. Generate `input.md` and `intake.json`.
5. Hand off artifacts to classification/planning flow.

## Validation
- Is the original input text preserved accurately?
- Are all required source fields present and normalized?
- Are output artifacts traceable to a run ID and source ID?
