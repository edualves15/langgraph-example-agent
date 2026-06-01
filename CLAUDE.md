# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

- **Python**: 3.12 (system command: `py -3.12`; venv command: `python`)
- **Virtual env**: Always activate `.venv` before running any command.

```bash
# Git Bash — ativar o ambiente virtual (obrigatório)
source .venv/Scripts/activate

# PowerShell — ativar o ambiente virtual (obrigatório)
.venv\Scripts\activate

# PowerShell — ou usar o python do venv diretamente, sem ativar
.venv\Scripts\python.exe -m v2.main

# Recriar o .venv do zero (se necessário)
py -3.12 -m venv .venv
```

## Commands

```bash
# Install
pip install -e .
pip install -e ".[dev]"   # includes pytest

# Run (production)
uvicorn app.main:app --port 8000

# Run (dev, auto-reload on app/ changes)
uvicorn app.main:app --reload --reload-dir app --port 8000

# Tests
pytest tests/

# Single test
pytest tests/test_calculator.py::test_calculator
```

## Running v2

```bash
# Executa o script standalone (precisa de GEMINI_API_KEY no .env)
python -m v2.main
```

## Architecture

Two independent entry points coexist:

- **`app/`** — production FastAPI microservice with LangGraph orchestration
- **`v2/main.py`** — standalone async script; uses `StreamWriter` + `NarrationAdapter` with `astream(stream_mode=["custom", "messages"])` for rich structured status events aligned with AG-UI protocol; no HTTP layer

### `app/` request flow

```
POST /chat  →  AgentService.run()  →  LangGraph graph  →  answer
POST /chat/stream  →  AgentService.stream()  →  SSE events
```

The LangGraph graph (`app/agent/graph.py`) has two nodes in a loop:

```
START → agent_node → [has tool_calls?] → tools_node → agent_node → ... → END
```

- `agent_node` (`app/agent/nodes.py`): prepends the system prompt, calls the LLM
- `tools_node`: LangGraph's built-in `ToolNode` with retry (max 2 attempts per tool)
- `route_after_agent` (`app/agent/edges.py`): breaks the loop once `ToolMessage` count reaches `MAX_TOOL_CALLS`
- `AgentState` (`app/agent/state.py`): a single `messages` list; state is ephemeral (lives only for the duration of one request)

### LLM provider selection

`app/services/llm_service.py` is the single place to swap providers. Controlled by `LLM_PROVIDER` in `.env`:
- `gemini` → `ChatGoogleGenerativeAI` (default)
- `proprietary` → `ChatOpenAI` with custom `base_url` (OpenAI-compatible APIs)

### Adding tools

1. Create `app/tools/my_tool.py` using `@tool` from `langchain_core.tools`
2. Register in `app/registries/tool_registry.py` → `get_local_tools()`
3. Optionally add `metadata` dict on the tool object for streaming UI labels (see below)

Web search (`web_search`, `web_extract`) is loaded only when `TAVILY_API_KEY` is set.

MCP tools are loaded at startup via `app/mcp/client.py` when `MCP_ENABLED=true`.

### Tool metadata for streaming

The `/chat/stream` SSE endpoint emits `step` events while tools run. Tools can customize these labels by setting a `metadata` dict after tool definition:

```python
my_tool.metadata = {
    "step_label": "Static label...",          # shown when tool is called
    "step_label_template": "Processing {arg}...",  # formatted with tool call args
    "step_done_label": "Done",                # shown after tool returns OK
    "step_error_label": "Failed",             # shown on tool error
    "step_icon": "search",                    # icon key for the UI
    "step_category": "web",                   # category for UI grouping
}
```

The `_process_step` function in `app/services/agent_service.py` reads this metadata.

### Error classification

`app/exceptions.py` defines domain errors (`QuotaExceededError`, `ProviderAuthError`, `AgentRuntimeError`). `agent_service.py` inspects HTTP status codes from provider exceptions and re-raises the appropriate domain error, which FastAPI handlers in `app/main.py` map to 503/502/500 responses.

## Environment variables

Copy `.env.example` to `.env`. Required keys:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `proprietary` |
| `GEMINI_API_KEY` | — | Required when provider is `gemini` |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Model name |
| `TAVILY_API_KEY` | — | Enables `web_search` / `web_extract` tools |
| `MAX_TOOL_CALLS` | `10` | Per-request tool call cap |
| `MCP_ENABLED` | `false` | Enable MCP server integration |
| `MCP_SERVERS_JSON` | `{}` | JSON map of MCP server configs |
