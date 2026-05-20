# AI Delivery Hub

LangGraph MVP for human-initiated delivery planning. The graph classifies pasted request text, generates delivery artifacts, writes audit logs, and stops at a human approval gate.

## Setup

Install dependencies:

```bash
uv sync
```

Create `.env` from the example:

```bash
cp .env.example .env
```

Fill in Azure OpenAI values:

```text
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-chat-model-deployment
AZURE_OPENAI_MODEL_NAME=gpt-5.1
AZURE_OPENAI_API_KEY=your_azure_openai_key
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

If your organization exposes Azure OpenAI through an OpenAI-compatible API Management endpoint ending in `/openai/v1`, use that endpoint and put the model/deployment name in `AZURE_OPENAI_DEPLOYMENT`.
`AZURE_OPENAI_MODEL_NAME` is optional, but useful for Langfuse cost attribution when an Azure deployment name is not the canonical model name.

Optional per-stage model routing:

```text
AZURE_OPENAI_CLASSIFICATION_DEPLOYMENT=gpt-5-mini
AZURE_OPENAI_REQUIREMENTS_DEPLOYMENT=gpt-5.1
AZURE_OPENAI_ARCHITECTURE_DEPLOYMENT=gpt-5.4
AZURE_OPENAI_PLANNING_DEPLOYMENT=gpt-5.1
AZURE_OPENAI_REVIEW_DEPLOYMENT=gpt-5.4
AZURE_OPENAI_QA_DEPLOYMENT=gpt-5.1
AZURE_OPENAI_DOCUMENTATION_DEPLOYMENT=gpt-5-mini
AZURE_OPENAI_REVISION_DEPLOYMENT=gpt-5.1
AZURE_OPENAI_DRAFT_DEPLOYMENT=gpt-5-mini
```

Any missing stage-specific value falls back to `AZURE_OPENAI_DEPLOYMENT`.

Optional Langfuse tracing for local runs:

```text
LANGFUSE_ENABLED=true
LANGFUSE_MANUAL_GENERATIONS=true
LANGFUSE_CAPTURE_IO=true
LANGFUSE_BASE_URL=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-your-project-public-key
LANGFUSE_SECRET_KEY=sk-lf-your-project-secret-key
```

Create these project keys in your Langfuse project settings. Once these values are set in `.env`, tracing is applied automatically to LangGraph Studio/server, CLI, MCP, and the simple prompt example. Set `LANGFUSE_ENABLED=false` to disable tracing locally without removing keys.

For the Langfuse dashboard cost panels, the app sends explicit generation `usage_details`. Cost is calculated by Langfuse if your model name matches a configured model definition. If you want a local fallback, add per-1K token rates:

```text
LANGFUSE_INPUT_COST_PER_1K_TOKENS_USD=0.00
LANGFUSE_OUTPUT_COST_PER_1K_TOKENS_USD=0.00
```

If your Azure deployments use custom names, map them to Langfuse model names:

```text
LANGFUSE_MODEL_NAME_GPT_5_1=gpt-5.1
LANGFUSE_MODEL_NAME_GPT_5_MINI=gpt-5-mini
LANGFUSE_MODEL_NAME_GPT_5_4=gpt-5.4
```

To sync Langfuse model prices dynamically from Azure Retail Prices API, configure meter regexes and run:

```text
AZURE_OPENAI_PRICING_REGION=eastus2
AZURE_PRICE_REGEX_GPT_5_1_INPUT=GPT 5\.1.*inp.*Gl.*1M Tokens
AZURE_PRICE_REGEX_GPT_5_1_OUTPUT=GPT 5\.1.*opt.*Gl.*1M Tokens
AZURE_PRICE_REGEX_GPT_5_MINI_INPUT=5\.4 mini.*Inp.*Gl.*1M Tokens
AZURE_PRICE_REGEX_GPT_5_MINI_OUTPUT=5\.4 mini.*Opt.*Gl.*1M Tokens
AZURE_PRICE_REGEX_GPT_5_4_INPUT=5\.4(?! mini).*inp.*Gl.*1M Tokens
AZURE_PRICE_REGEX_GPT_5_4_OUTPUT=5\.4(?! mini).*opt.*Gl.*1M Tokens
```

```bash
uv run python scripts/sync_langfuse_azure_prices.py
```

The script fetches current Azure prices for matching meter names and upserts Langfuse custom model definitions for `gpt-5.1`, `gpt-5-mini`, and `gpt-5.4`.

## Run

Simple one-call interactive Azure OpenAI example:

```bash
uv run python examples/simple_interactive.py
```

Full delivery-hub workflow:

```bash
uv run python examples/run_delivery_hub.py --input examples/sample_ticket.md
```

Installed console script equivalent:

```bash
uv run delivery-hub-cli --interactive --timeout 180
```

At the approval gate, the CLI prints generated artifact paths and asks:

```text
Choose: [a]pprove all, [m]odify files, [r]eject:
```

Choose `a` to approve all generated artifacts, `m` to describe changes that should be applied to the generated markdown files, or `r` to reject.

Approve every generated artifact automatically:

```bash
uv run python examples/run_delivery_hub.py --input examples/sample_ticket.md --approve-all
```

Approval writes `approval.json` into the run artifact folder.
Modification requests write `modifications.json` into the run artifact folder.

Interactive paste mode:

```bash
uv run python examples/run_delivery_hub.py --interactive
```

Type one request line and press `Enter`.

Multi-line paste mode:

```bash
uv run python examples/run_delivery_hub.py --paste
```

Paste the request text, then press `Ctrl+D`.

Artifacts are written to:

```text
artifacts/runs/<run_id>/
```

## LangGraph Server

```bash
uv run langgraph dev
```

If Langfuse env vars are configured, LangGraph Server runs are traced automatically to `LANGFUSE_BASE_URL`. Traces use stable names such as `ai-delivery-hub-studio`, `ai-delivery-hub-cli`, `ai-delivery-hub-mcp`, and stage tags such as `stage:classify` or `artifact:architecture.md`. Open a trace in Langfuse Tracing to inspect the graph-like execution hierarchy and nested generation observations.

Available Studio assistants:

- `agent`: `AI Delivery Hub Workflow (Graph)` for the full workflow graph and raw JSON input.
- `agent_chat`: `AI Delivery Hub Workflow (Chat)` for the Chat tab.

Invoke graph `agent` with input:

```json
{"input_text":"Implement Adobe Commerce checkout telemetry improvements.","source_type":"manual_prompt"}
```

When Studio reaches the interrupt, resume with:

```json
{"approved": true, "reviewer_note": "Approved for QA execution"}
```

or reject with:

```json
{"approved": false, "reviewer_note": "Needs more detail"}
```

## MCP Server

Run the delivery hub as a local MCP stdio server:

```bash
uv run delivery-hub-mcp
```

Available MCP tools:

- `draft_delivery`: creates a fast one-call delivery brief without running the full graph.
- `plan_delivery`: starts an interactive delivery run and returns a `run_id`.
- `continue_delivery`: advances one stage, revises artifacts, approves, or rejects.
- `review_delivery`: reviews artifact paths, classification, audit, approval, and modification status.
- `revise_delivery`: revises generated delivery artifacts using reviewer instructions.
- `approve_delivery`: approves or rejects a pending delivery run.

Available MCP prompt:

- `run_delivery_workflow`: instructs the chat agent to run the full workflow by chaining short MCP calls in one chat turn.

Example professional flow:

1. Use `draft_delivery` for a fast brief when the MCP client has a short timeout.
2. Use `plan_delivery` when you need persisted artifacts and approval gates.
3. Use `continue_delivery` with action `continue` to run one stage at a time.
4. Use `continue_delivery` with action `revise` if artifacts need changes.
5. Use `continue_delivery` with action `approve` or `reject` when the output is acceptable.

Interactive MCP example:

```text
Use the run_delivery_workflow prompt for this request:
Plan Adobe Commerce observer logic that adds a GUID to sales_order when an order is placed.
```

If your client does not expose MCP prompts, use this plain chat instruction:

```text
Run the AI Delivery Hub workflow for this request in one chat. Use plan_delivery first, then call continue_delivery with action "continue" repeatedly until status is awaiting_approval. Do not ask me between stages unless a stage fails. When awaiting approval, summarize artifact paths and ask me to approve, revise, or reject.

Request:
Plan Adobe Commerce observer logic that adds a GUID to sales_order when an order is placed.
```

Example MCP client configuration:

```json
{
  "mcpServers": {
    "ai-delivery-hub": {
      "command": "uv",
      "args": ["run", "delivery-hub-mcp"],
      "cwd": "/home/bogdan/Projects/commerce-ai-hub/app"
    }
  }
}
```

## Tests

```bash
uv run pytest -q
```
