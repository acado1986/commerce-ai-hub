# Installation Guide

## What You Need

- Linux/macOS shell (or Windows with WSL)
- Python `>=3.10`
- `uv` package manager: https://docs.astral.sh/uv/
- LangGraph CLI (installed via project dependencies and run with `uv run langgraph`)
- Azure OpenAI access:
  - endpoint
  - deployment/model name
  - API key

Optional:

- Docker (for local Postgres checkpointer)
- Langfuse project keys (for tracing)

## 1. Install Dependencies

From the repository root:

```bash
uv sync
```

This installs app dependencies plus LangGraph tooling from the dev dependency group
(including `langgraph-cli[inmem]`).

Verify LangGraph CLI is available:

```bash
uv run langgraph --help
```

## 2. Configure Environment

Create local env file:

```bash
cp .env.example .env
```

Set required Azure OpenAI values in `.env`:

```text
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-chat-model-deployment
AZURE_OPENAI_API_KEY=your_azure_openai_key
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

Recommended:

```text
AZURE_OPENAI_MODEL_NAME=gpt-5.1
```

If using OpenAI-compatible APIM proxy:

```text
AZURE_OPENAI_ENDPOINT=https://your-apim-host/path/openai/v1
AZURE_OPENAI_DEPLOYMENT=gpt-5.1
```

## 3. Optional: Durable Checkpointer (Postgres)

Start local Postgres:

```bash
docker compose -f docker-compose.postgres.yml up -d
```

Set one env var in `.env`:

```text
LANGGRAPH_CHECKPOINTER_POSTGRES_URI=postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable
# or
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable
```

Stop Postgres:

```bash
docker compose -f docker-compose.postgres.yml down
```

## 4. Optional: Langfuse Tracing

Enable in `.env`:

```text
LANGFUSE_ENABLED=true
LANGFUSE_MANUAL_GENERATIONS=true
LANGFUSE_CAPTURE_IO=true
LANGFUSE_BASE_URL=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-your-project-public-key
LANGFUSE_SECRET_KEY=sk-lf-your-project-secret-key
```

If you do not use Langfuse, keep `LANGFUSE_ENABLED=false`.

## 5. Verify Installation

Run a quick config check:

```bash
uv run delivery-hub-cli --check-config
```

Run a sample workflow:

```bash
uv run python examples/run_delivery_hub.py --input examples/sample_ticket.md
```

Generated artifacts should appear in:

```text
artifacts/runs/<run_id>/
```

## 6. Useful Commands

Run LangGraph Studio/server:

```bash
uv run langgraph dev
```

Run CLI interactively:

```bash
uv run delivery-hub-cli --interactive --timeout 180
```

Run tests:

```bash
uv run pytest
```
