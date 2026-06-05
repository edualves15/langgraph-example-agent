# langgraph-private-agent

Base **reutilizável** de um agente **LangGraph** exposto pelo **protocolo oficial AG-UI**
(Agent-User Interaction) sobre **FastAPI**, com uma página de chat de demonstração que usa
o cliente oficial `@ag-ui/client` e **UI generativa** interativa.

A integração LangGraph → AG-UI é feita **inteiramente pela biblioteca oficial**
`ag-ui-langgraph` (sem adaptadores SSE caseiros). O domínio de exemplo é um **atendente de
restaurante** (cardápio + reservas); trocar de domínio é trocar as tools de backend.

- **Provedor LLM:** Gemini (`langchain-google-genai`) — ponto único de troca em
  `app/services/llm_service.py`.
- **Sem build step no front:** `web/` é servido estaticamente pelo próprio FastAPI.

---

## Índice

- [Quickstart](#quickstart)
- [Arquitetura](#arquitetura)
- [Eventos AG-UI (wire format)](#eventos-ag-ui-wire-format)
- [Estrutura de pastas](#estrutura-de-pastas)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Como estender](#como-estender)
- [Trocar de domínio](#trocar-de-domínio)
- [MCP](#mcp-model-context-protocol)
- [Testes](#testes)
- [Segurança](#segurança)
- [Conformidade com padrões oficiais](#conformidade-com-padrões-oficiais)

---

## Quickstart

Requer Python 3.12.

```bash
pip install -e ".[dev]"          # inclui pytest
cp .env.example .env             # defina ao menos GEMINI_API_KEY

# Produção
uvicorn app.main:app --port 8000

# Dev (auto-reload nas mudanças de app/)
uvicorn app.main:app --reload --reload-dir app --port 8000
```

Abra `http://localhost:8000/` para o chat de demonstração.

Endpoint AG-UI (POST, SSE). O corpo é um `RunAgentInput` (campos camelCase):

```bash
curl -N -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" -H "Accept: text/event-stream" \
  -d '{"threadId":"t1","runId":"r1","state":{},"messages":[{"id":"m1","role":"user","content":"quanto é 15 * 4?"}],"tools":[],"context":[],"forwardedProps":{}}'
```

Rotas: `POST /agent` (SSE) · `GET /agent/health` · `GET /health`.

---

## Arquitetura

### Fluxo de request

`app/main.py` cria o `FastAPI(lifespan=...)`, registra o middleware e inclui os routers.
No **lifespan** (padrão oficial para recursos async) as tools MCP são carregadas, o grafo é
construído e o agente fica em `app.state.agent`.

| Componente | Onde | Função |
|---|---|---|
| `POST /agent` | `app/routers/agent.py` | Stream SSE: `agent.clone().run(input)` + `EventEncoder`, com **wrap de `RUN_ERROR`** |
| `GET /agent/health`, `GET /health` | `app/routers/agent.py`, `health.py` | Health checks |
| CORS + limite de corpo | `app/middleware.py` | `configure_middlewares(app)` |
| Página estática | `app/main.py` | `StaticFiles` montado em `/` por último |

### Grafo (`app/agent/graph.py`)

Um `StateGraph` **custom** (loop ReAct) — não o prebuilt `create_react_agent`, porque é
preciso distinguir dois tipos de tool:

- **Tools de backend** (executadas no servidor): vinculadas ao LLM e rodadas num `ToolNode`.
- **Tools de frontend** (anunciadas pelo cliente em runtime via `RunAgentInput.tools`):
  vinculadas ao LLM como schemas, mas **executadas no navegador**.

O nó `agent` vincula backend + schemas de frontend; o roteamento executa no servidor apenas
chamadas de tools de backend, enquanto uma chamada a tool de frontend **encerra o run** —
o navegador executa a ação e retoma com um `ToolMessage` no run seguinte.

O `state_schema` (`app/agent/state.py`) adiciona, além de `messages`/`remaining_steps`:
`tools` (frontend tools do handshake), `order` e `reservation` (estado compartilhado do
domínio). O `checkpointer` é `MemorySaver` (necessário para threads e human-in-the-loop).

### Frontend genérico (`web/`)

Cliente AG-UI **agnóstico de agente**: renderiza apenas com o que o protocolo fornece em
runtime (eventos SSE via `@ag-ui/client`).

- `app.js` — cria `HttpAgent({ url: "/agent" })`, assina os eventos, mantém uma bolha por
  `runId`, renderiza o painel de estado genericamente e executa as tools de frontend.
- `frontend-tools.js` — tools de **UI genéricas** anunciadas ao agente: `present_cards`,
  `present_options`, `confirm_dialog`. O `handler(args, { container })` renderiza inline no
  chat, aguarda a interação e devolve a string que vira o `ToolMessage`.
- `ui-components.js` — widgets genéricos (cards, opções, dialog) que resolvem uma `Promise`
  na interação. Anti-XSS (escapam todo conteúdo).
- `markdown.js` — renderizador Markdown próprio (sem libs), com escape e sanitização de URL.

---

## Eventos AG-UI (wire format)

`type` em **SCREAMING_SNAKE_CASE**, campos em **camelCase**, SSE `text/event-stream`:

- **Lifecycle:** `RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR`, `STEP_STARTED`/`STEP_FINISHED`.
- **Texto:** `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT` (`delta`), `TEXT_MESSAGE_END`.
- **Tools:** `TOOL_CALL_START`, `TOOL_CALL_ARGS` (`delta`), `TOOL_CALL_END`, `TOOL_CALL_RESULT`.
- **Estado:** `STATE_SNAPSHOT`, `STATE_DELTA` (JSON Patch), `MESSAGES_SNAPSHOT`.
- **Especiais:** `CUSTOM` (`name`,`value`) — interrupts chegam como `name="on_interrupt"`,
  estado preditivo como `name="PredictState"`; `RAW` (passthrough de eventos LangGraph,
  omitível via `AG_UI_STREAM_RAW_EVENTS=false`).

---

## Estrutura de pastas

```
app/
  main.py            FastAPI + lifespan (agente em app.state) + routers + middleware
  config.py          Settings (pydantic-settings)
  middleware.py      CORS + limite de corpo (configure_middlewares)
  errors.py          describe_error (cliente) / error_hint (log)
  routers/           agent.py (POST /agent, GET /agent/health) · health.py (GET /health)
  agent/             graph.py (StateGraph custom) · state.py · prompts/ (system.md)
  registries/        tool_registry.py (tools locais + PREDICT_STATE)
  services/          llm_service.py (Gemini) · mcp_service.py (mcp.json)
  tools/             calendar · math · restaurant · web_search (Tavily, opcional)
web/                 app.js + frontend-tools.js + ui-components.js + markdown.js + estáticos
tests/               unit + integração (servidor)
mcp.json             servidores MCP (mcpServers), vazio por padrão
```

---

## Variáveis de ambiente

Copie `.env.example` para `.env`.

| Variável | Default | Descrição |
|---|---|---|
| `GEMINI_API_KEY` | — | **Obrigatória** (provedor Gemini) |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Nome do modelo |
| `TAVILY_API_KEY` | — | Habilita as tools de busca web (`web_search`/`web_extract`) |
| `AG_UI_STREAM_RAW_EVENTS` | `true` | Se `false`, omite eventos `RAW` do SSE |
| `AG_UI_CORS_ORIGINS` | `*` | Origens permitidas via CORS (CSV). `*` libera todas |
| `AG_UI_MAX_BODY_BYTES` | `2000000` | Tamanho máx. do corpo (bytes). `0` desabilita |

---

## Como estender

### Tool de backend (efeito/dado server-side)

1. Crie `app/tools/minha_tool.py` com `@tool` do `langchain_core.tools`.
2. Registre em `app/registries/tool_registry.py` → `get_local_tools()`.

A **docstring** (ou `description=`) é o que o modelo lê para decidir quando/como usar a
tool — invista nela. Padrão sugerido (em inglês):

```
<resumo de 1 linha>
Use this tool when: <gatilhos>.
Input:
- <arg> — <tipo, restrições>   (apenas args do modelo; NÃO documente injeções)
Returns <forma do retorno>.
```

### Tool de frontend (executada no navegador)

Não crie `@tool` no backend. As tools de UI genéricas (`present_cards`/`present_options`/
`confirm_dialog`) já existem em `web/frontend-tools.js`; o agente as descobre no handshake e
passa os dados do domínio. Para um novo widget, adicione-o a `web/ui-components.js` e exponha
uma tool em `frontend-tools.js`.

### Estado compartilhado (agente-owned)

Uma tool muta o estado retornando `Command(update={"<chave>": ..., "messages": [...]})` com
`InjectedState`/`InjectedToolCallId`; a lib emite `STATE_SNAPSHOT`/`STATE_DELTA` e o front
renderiza no painel de estado. Exemplo: `update_reservation` muta `order` e `reservation`.

### Human-in-the-loop

Chame `interrupt(value)` (`langgraph.types`) dentro da tool de ação (ver `create_reservation`);
a retomada vem por `Command(resume=...)`. Deixe o `value` **legível** (rótulos amigáveis) — o
front o renderiza como "Rótulo: valor".

### Estado preditivo (`PredictState`)

`PREDICT_STATE` (em `tool_registry.py`) liga uma chave de estado ao argumento de uma tool; o
nó `agent` injeta isso como metadata, a lib emite `CUSTOM PredictState` e o front aplica os
args em streaming de forma otimista, reconciliando no snapshot. O efeito visível depende de o
provedor fazer streaming dos `TOOL_CALL_ARGS`.

---

## Trocar de domínio

O domínio vive **só no backend**: troque `app/tools/restaurant_tools.py` e o bloco
`RESTAURANT_TOOLS` (+ `PREDICT_STATE`) em `app/registries/tool_registry.py`, e ajuste a
persona em `app/agent/prompts/system.md`. As tools de calendário e cálculo permanecem; o
frontend é genérico e não muda.

---

## MCP (Model Context Protocol)

Servidores MCP são lidos de **`mcp.json`** na raiz (convenção `mcpServers`), via
`langchain-mcp-adapters` (`MultiServerMCPClient`). Por padrão está **vazio**. Para habilitar,
adicione entradas — as tools entram no grafo automaticamente (`build_graph(extra_tools=...)`):

```json
{
  "mcpServers": {
    "meu_servidor": { "url": "https://host/mcp", "transport": "streamable_http" }
  }
}
```

---

## Testes

Suíte do **servidor** (unit + integração), determinística e **offline** — o LLM nunca é
chamado (os testes de integração injetam um agente stubado).

```bash
pytest tests/                                    # tudo
pytest tests/test_api.py                         # só integração
pytest tests/test_math_tools.py::test_basic_operators
```

Cobre: tools (math incl. guarda de DoS, calendário, restaurante), erros (sem vazamento de
detalhe), config/registry/prompts/MCP, conversão de schemas e compilação do grafo, o
middleware de limite de corpo, e os endpoints HTTP (health, CORS, validação 422, streaming
SSE, wrap de `RUN_ERROR`, filtro de `RAW`).

---

## Segurança

> Sem autenticação por padrão — **não exponha publicamente** sem adicionar auth + rate-limit.

Mitigações implementadas:

- **Anti-XSS:** Markdown e componentes de UI escapam todo conteúdo do agente e sanitizam
  URLs (só http/https/mailto).
- **DoS de potência:** `math_tools` recusa `**` de magnitude descomunal (ex.: `9**9**9`).
- **Sem vazamento de erro:** o cliente recebe mensagens genéricas (`describe_error`); o
  detalhe vai só ao log (`error_hint`).
- **Limite de corpo:** `MaxBodySizeMiddleware` (ASGI, não bufferiza o SSE) recusa POST acima
  de `AG_UI_MAX_BODY_BYTES` (413).
- Sem `eval/exec/subprocess`; `math` é AST-safe; `.env` é gitignored.

Limitações conhecidas (requerem auth/infra para produção): CORS `*` sem auth permite qualquer
origem acionar o agente; `MemorySaver` é in-memory e ilimitado (por `threadId`); `threadId`
não tem isolamento; conteúdo de busca web é não-confiável (prompt injection, com blast radius
limitado — sem tools destrutivas e sem SSRF local).

---

## Conformidade com padrões oficiais

- **Wire AG-UI:** `EventEncoder` (eventos `type` SCREAMING_SNAKE_CASE, campos camelCase) +
  tipos oficiais `ag_ui.core.types` (`RunAgentInput`/`Tool`).
- **Endpoint:** replica o helper oficial `add_langgraph_fastapi_endpoint`
  (`agent.clone().run` + `EventEncoder`), com wrap de `RUN_ERROR`.
- **Tools de frontend:** descobertas via `RunAgentInput.tools` e executadas no navegador,
  devolvendo `ToolMessage` — o padrão oficial de client-side tools.
- **Estado preditivo:** `PredictState` (equivalente ao `StateStreamingMiddleware`).
- **CORS:** `CORSMiddleware` (credenciais só com origens explícitas, conforme a spec).
- **MCP:** `langchain-mcp-adapters` (`MultiServerMCPClient`) + convenção `mcpServers`.
- **Estrutura FastAPI:** `APIRouter`/`include_router`, middleware isolado, `lifespan` para
  recursos async.

---

Notas internas de manutenção e decisões de design ficam em [`CLAUDE.md`](./CLAUDE.md).
