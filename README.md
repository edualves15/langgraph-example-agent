# langgraph-private-agent

Agente **LangGraph** exposto via **protocolo oficial AG-UI** (Agent-User Interaction)
sobre **FastAPI**, usando a integração oficial `ag-ui-langgraph` e o cliente oficial
`@ag-ui/client`. Inclui uma página de demonstração (chat) com **UI generativa** interativa.

O domínio de exemplo é um **atendente de restaurante** (cardápio + reservas) — trocar de
domínio = trocar as tools de backend (`app/tools/restaurant_tools.py` + o registry).

## Quickstart

```bash
pip install -e ".[dev]"
cp .env.example .env          # defina GEMINI_API_KEY
uvicorn app.main:app --port 8000
# abra http://localhost:8000/
```

Endpoint AG-UI: `POST /agent` (SSE de eventos canônicos). Health: `GET /health`,
`GET /agent/health`.

## Capacidades demonstradas

- **Streaming** de texto + ciclo de vida (`RUN_*`, `TEXT_MESSAGE_*`).
- **Tools de backend** (executadas no servidor): cardápio, datas, cálculo, reservas.
- **UI generativa interativa** (tools de **frontend**, renderizadas inline no chat):
  lista de **cards**, **opções** (checkbox/radio) e **dialog** Sim/Não — o agente as
  descobre em runtime (handshake) e prefere oferecê-las a perguntar em texto.
- **Estado compartilhado** ao vivo (`STATE_SNAPSHOT`/`STATE_DELTA`): o painel reflete o
  **rascunho da reserva** (pratos + data + horário + pessoas) conforme o cliente escolhe.
- **Estado preditivo** (`PredictState`): preview otimista do estado a partir dos args em
  streaming (depende do provedor; reconcilia no snapshot).
- **Human-in-the-loop** (interrupts): aprovação de reserva num modal **legível** (sem JSON).
- **CORS**: qualquer frontend AG-UI de outra origem pode consumir o agente.
- **MCP** (scaffold): servidores via `mcp.json` (`mcpServers`), hoje vazio — pronto p/ ligar.

## Estrutura

```
app/
  main.py            FastAPI + lifespan (cria o agente em app.state) + routers + middleware
  middleware.py      CORS (configure_middlewares)
  routers/           agent.py (POST /agent, GET /agent/health) · health.py (GET /health)
  agent/             graph.py (StateGraph custom) · state.py · prompts/
  registries/        tool_registry.py (tools locais + PREDICT_STATE)
  services/          llm_service.py (Gemini) · mcp_service.py (mcp.json)
  tools/             calendar · math · restaurant · web_search (Tavily, opcional)
web/                 cliente AG-UI genérico (app.js) + UI tools (frontend-tools.js,
                     ui-components.js) + markdown.js — sem build step
```

## Conformidade com padrões oficiais

- **Wire AG-UI**: serialização via `EventEncoder` (eventos com `type` em SCREAMING_SNAKE_CASE,
  campos camelCase); entrada tipada com `ag_ui.core.types.RunAgentInput` / `Tool`.
- **Endpoint**: replica o helper oficial `add_langgraph_fastapi_endpoint`
  (`agent.clone().run(input)` + `EventEncoder`), com um **wrap de `RUN_ERROR`** (evento
  canônico do protocolo) para resiliência.
- **Tools de frontend**: descobertas via `RunAgentInput.tools` (handshake) e executadas no
  navegador, devolvendo `ToolMessage` — o padrão oficial para client-side tools.
- **Estado preditivo**: `PredictState` (equivalente ao `StateStreamingMiddleware`).
- **CORS**: `CORSMiddleware` do FastAPI (credenciais só com origens explícitas, conforme a spec).
- **MCP**: `langchain-mcp-adapters` (`MultiServerMCPClient`) + convenção `mcpServers`.
- **Estrutura FastAPI**: `APIRouter`/`include_router`, middleware isolado, `lifespan` para
  recursos async — a estrutura de referência da documentação.

Detalhes de arquitetura e decisões em [`CLAUDE.md`](./CLAUDE.md).
