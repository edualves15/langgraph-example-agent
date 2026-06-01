# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Mantenha este arquivo sempre atualizado.** Sempre que adicionar, remover ou mudar arquivos, ferramentas, variáveis de ambiente, comandos ou decisões arquiteturais relevantes, atualize as seções correspondentes aqui antes de encerrar a tarefa.

## Environment

- **Python**: 3.12 (system command: `py -3.12`; venv command: `python`)
- **Virtual env**: Always activate `.venv` before running any command.

```bash
# Git Bash — ativar o ambiente virtual (obrigatório)
source .venv/Scripts/activate

# PowerShell — ativar o ambiente virtual (obrigatório)
.venv\Scripts\activate

# PowerShell — ou usar o python do venv diretamente, sem ativar
.venv\Scripts\python.exe -m pytest tests/

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
pytest tests/test_calculator.py::test_calculate_math_expression

# Health check
curl http://localhost:8000/health

# Nota: em PowerShell use aspas duplas escapadas: -d "{\"message\": \"...\"}"
# Em bash/WSL use aspas simples normalmente.

# Chat (sync) — aciona 1 tool
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "quanto é 15 * 4?"}'

# Chat (SSE streaming) — aciona 1 tool
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "que dia é hoje e quantos dias faltam para o natal?"}'

# Chat (SSE streaming) — força múltiplos steps (math + calendário + web search)
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Qual a data de hoje? Quantos dias úteis faltam até 31/12/2025? Se eu trabalhar 8h por dia, quantas horas úteis são essas no total? Pesquise também qual foi o PIB do Brasil em 2024."}'
```

## Architecture

Single entry point: **`app/`** — FastAPI microservice with LangGraph orchestration, NarrationAdapter streaming, and tool narration system.

### Request flow

```
POST /chat        →  AgentService.run()    →  graph.ainvoke()      →  answer
POST /chat/stream →  AgentService.stream() →  graph.astream_events(v2) + NarrationAdapter →  SSE events
GET  /health      →  {"status": "ok"}
```

### LangGraph graph (`app/agent/graph.py`)

```
START → agent_node → should_continue → tools_node → agent_node → ... → END
```

- `agent_node` (`app/agent/nodes.py`): prepends system prompt, calls LLM, emits `tool_call` custom events via `adispatch_custom_event`
- `tool_node` (`app/agent/nodes.py`): executes tools, emits `tool_result` / `tool_error` custom events with timing
- `should_continue` (`app/agent/edges.py`): routes to `tools` or `END`; breaks loop when `ToolMessage` count reaches `MAX_TOOL_CALLS`
- `AgentState` (`app/agent/state.py`): `messages: Annotated[list, operator.add]`; ephemeral per request

### Narration system (`app/narration/`)

Translates `graph.astream_events(version="v2")` into typed `NarrationEvent` objects (or raw `str` tokens).

- `events.py` — `NarrationEvent` dataclass (framework-agnostic, JSON-serializable)
- `adapter.py` — `NarrationAdapter`: async iterator, LangGraph events → `NarrationEvent | str`
- `consumer.py` — terminal renderer for local development

`AgentService.stream()` feeds the adapter and maps events to SSE:

| NarrationEvent type | SSE `_event` | payload fields |
|---|---|---|
| `tool_call` (stage=start) | `step` | `status="running"`, `text`, `icon`, `tool_name`, `block_id` |
| `tool_result` | `step` | `status="done"`, `text`, `icon`, `tool_name`, `duration_ms` |
| `error` | `step` | `status="error"`, `text`, `icon`, `tool_name`, `error` |
| `reasoning_started` | `step` | `status="thinking"`, `text`, `icon` |
| `run_finished` | — | terminates loop, triggers `done` event |
| `str` (token) | — | accumulated into answer buffer |
| final | `done` | `answer` |

### Adding tools

1. Create `app/tools/my_tool.py` using `@tool` from `langchain_core.tools`
2. Attach `NarrationMeta` for streaming labels:

```python
from app.tools import NarrationMeta

object.__setattr__(my_tool, "narration", NarrationMeta(
    icon="🔧",
    announce_template="Executando {arg}...",
    done_label="Concluído",
    error_label="Falhou",
))
```

3. Register in `app/registries/tool_registry.py` → `get_local_tools()`

`web_search` and `web_extract` (Tavily) are loaded only when `TAVILY_API_KEY` is set.

### Tool metadata fallback

`get_tool_narration()` in `app/tools/__init__.py` prefers `.narration` (NarrationMeta) and falls back to the LangChain `.metadata` dict (`step_label`, `step_done_label`, `step_icon`, etc.) for backward compatibility.

### LLM provider

`app/services/llm_service.py` — single place to swap providers. Currently: Gemini only (`ChatGoogleGenerativeAI`).

### Error classification

`app/exceptions.py` defines `QuotaExceededError`, `ProviderAuthError`, `AgentRuntimeError`. `agent_service.py` inspects HTTP status codes and re-raises as domain errors. FastAPI handlers in `app/main.py` map these to 503/502/500.

## Environment variables

Copy `.env.example` to `.env`. Required keys:

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — | Required (Gemini provider) |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Model name |
| `TAVILY_API_KEY` | — | Enables `web_search` / `web_extract` tools |
| `MAX_TOOL_CALLS` | `10` | Per-request tool call cap |
