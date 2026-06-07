# langgraph-private-agent

Base **reutilizável** de um agente **LangGraph** exposto pelo **protocolo oficial AG-UI**
(Agent-User Interaction) sobre **FastAPI**, com uma página de chat de demonstração que usa
o cliente oficial `@ag-ui/client` e **UI generativa** interativa.

A integração LangGraph → AG-UI é feita **inteiramente pela biblioteca oficial**
`ag-ui-langgraph` (sem adaptadores SSE caseiros). O **negócio é um plug isolado**: o engine
genérico (`app/agent/`) recebe um `Domain` por injeção e nunca importa o domínio. O exemplo
é um **atendente de restaurante** (cardápio + reserva + delivery) em `app/domain/restaurant/`;
**trocar de domínio = criar outro pacote `app/domain/<nome>/` e mudar 1 import** em `main.py`.

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

`app/main.py` é o **composition root**: cria o `FastAPI(lifespan=...)`, registra o middleware
e inclui os routers — único lugar que conhece engine + domínio. No **lifespan** (padrão oficial
para recursos async) os servidores MCP (gerais + do domínio) são unidos e carregados, o grafo é
construído com `build_graph(DOMAIN, extra_tools=...)`, o agente fica em `app.state.agent` e as
dicas de UI do domínio em `app.state.ui_hints` (entregues ao front via evento `CUSTOM`).

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
o navegador executa a ação e retoma com um `ToolMessage` no run seguinte. As tools de backend
(genéricas + do domínio + MCP) passam por **dedup de nomes** (`_merge_backend_tools`): em
colisão, a tool de backend confiável vence e a externa/MCP é descartada.

`build_graph(domain, extra_tools=...)` é genérico — recebe o `Domain` (`app/agent/domain.py`:
`tools`, `state_schema`, `prompt`, `predict_state`, `ui_hints`, `mcp_servers`). O `state_schema`
base (`app/agent/state.py`) declara só `tools` (frontend tools do handshake) além de
`messages`/`remaining_steps`; o domínio o estende (ex.: `RestaurantState` adiciona `reservation`
e `delivery`, o estado compartilhado). O `checkpointer` é `MemorySaver` (threads + HITL).

### Frontend genérico (`web/`)

Cliente AG-UI **agnóstico de agente**: renderiza apenas com o que o protocolo fornece em
runtime (eventos SSE via `@ag-ui/client`).

- `app.js` — cria `HttpAgent({ url: "/agent" })`, assina os eventos, mantém uma bolha por
  `runId`, renderiza o painel de estado genericamente e executa as tools de frontend.
- `frontend-tools.js` — tools de **UI genéricas** anunciadas ao agente: `present_cards`,
  `present_options`, `present_buttons`, `present_number`, `confirm_dialog`. O
  `handler(args, { container })` renderiza inline no chat, aguarda a interação e devolve
  `{ content, display }` (`content` vira o `ToolMessage`; `display` é o balão do usuário).
  Os ícones/títulos do resumo de estado vêm do backend via `CUSTOM`/`ui_hints` (front genérico).
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
  estado preditivo como `name="PredictState"`, dicas de UI do domínio como `name="ui_hints"`
  (`{state_tag_icons, state_titles}`, emitido após o `RUN_STARTED`); `RAW` (passthrough de
  eventos LangGraph, omitível via `AG_UI_STREAM_RAW_EVENTS=false`).

---

## Estrutura de pastas

```
app/
  main.py            Composition root: FastAPI + lifespan + routers + middleware (importa DOMAIN)
  config.py          Settings (pydantic-settings)
  middleware.py      CORS + limite de corpo (configure_middlewares)
  errors.py          describe_error (cliente) / error_hint (log)
  routers/           agent.py (POST /agent, GET /agent/health) · health.py (GET /health)
  agent/             ENGINE genérico: graph.py · state.py (AgentState base) · domain.py (contrato
                       Domain) · prompts/ (system.md genérico + composição)
  registries/        tool_registry.py (só capabilities genéricas: calendário + math + web)
  services/          llm_service.py (Gemini) · mcp_service.py (load/merge/get + isolamento)
  tools/             calendar · math · web_search (Tavily, opcional) — genéricas, sem domínio
  domain/            PLUGS de negócio (cada um exporta um Domain)
    restaurant/      __init__.py (DOMAIN) · tools.py · state.py · ui_hints.py · prompt.md · mcp.json
web/                 app.js + frontend-tools.js + ui-components.js + markdown.js + estáticos
tests/               unit + integração (servidor)
mcp.json             servidores MCP GERAIS (mcpServers), vazio por padrão
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

- **Genérica (capability, sem domínio):** crie `app/tools/minha_tool.py` com `@tool` e
  registre em `app/registries/tool_registry.py` → `get_local_tools()`.
- **De domínio:** crie em `app/domain/<dominio>/tools.py` e adicione à lista de tools do
  `Domain` (ex.: `RESTAURANT_TOOLS` em `app/domain/restaurant/__init__.py`) — entra no grafo
  via `Domain.tools`, não pelo registry genérico.

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
`present_buttons`/`present_number`/`confirm_dialog`) já existem em `web/frontend-tools.js`; o
agente as descobre no handshake e passa os dados do domínio. Para um novo widget, adicione-o a
`web/ui-components.js` e exponha uma tool em `frontend-tools.js`.

### Estado compartilhado (agente-owned)

Uma tool muta o estado retornando `Command(update={"<chave>": ..., "messages": [...]})` com
`InjectedState`/`InjectedToolCallId`; a lib emite `STATE_SNAPSHOT`/`STATE_DELTA` e o front
renderiza no painel de estado. A chave é declarada no `state_schema` do domínio. Exemplo:
`update_reservation` muta `reservation` (`{items, date, time, party_size, customer_name}`).

### Human-in-the-loop

Chame `interrupt(value)` (`langgraph.types`) dentro da tool de ação (ver `create_reservation`);
a retomada vem por `Command(resume=...)`. Deixe o `value` **legível** (rótulos amigáveis) — o
front o renderiza como "Rótulo: valor".

### Estado preditivo (`PredictState`)

`Domain.predict_state` liga uma chave de estado ao argumento de uma tool; o nó `agent` injeta
isso como metadata, a lib emite `CUSTOM PredictState` e o front aplica os args em streaming de
forma otimista, reconciliando no snapshot. O efeito visível depende de o provedor fazer
streaming dos `TOOL_CALL_ARGS` (com Gemini é no-op; o estado segue via snapshot).

---

## Trocar de domínio

O domínio é um **plug** (`app/domain/<nome>/`) — o engine, o registry genérico, o adaptador
AG-UI e o frontend **não mudam**:

1. Crie `app/domain/<novo>/` com: `tools.py` (`@tool`s de backend), `state.py` (subclasse de
   `AgentState` com as chaves do domínio), `prompt.md` (papel/fluxos), `ui_hints.py`
   (ícones/títulos do resumo), `mcp.json` opcional (servidores MCP do domínio) e `__init__.py`
   exportando `DOMAIN = Domain(name, tools, state_schema, prompt, predict_state, ui_hints,
   mcp_servers)`.
2. Em `app/main.py`, troque o import por `from app.domain.<novo> import DOMAIN`.

O `system.md` é **genérico** (não tem negócio); o papel do domínio vai em `prompt.md`. As
capabilities genéricas (calendário, math, web) permanecem.

---

## MCP (Model Context Protocol)

Servidores MCP são carregados via `langchain-mcp-adapters` (`MultiServerMCPClient`) de **duas
origens**, unidas no lifespan e injetadas como `extra_tools` em `build_graph(DOMAIN, ...)`:

- **Gerais** (capabilities, sem domínio): `mcp.json` na raiz.
- **De domínio**: `app/domain/<dominio>/mcp.json` → `Domain.mcp_servers` (viaja com o plug).

Ambos usam a convenção `mcpServers` e ficam **vazios** por padrão. Para habilitar, adicione
entradas (sem mexer em código):

```json
{
  "mcpServers": {
    "meu_servidor": { "url": "https://host/mcp", "transport": "streamable_http" }
  }
}
```

**Robustez/segurança:**

- **Isolamento de falha:** cada servidor é carregado individualmente; um servidor
  inacessível/mal configurado é **logado e pulado**, sem derrubar a inicialização.
- **Dedup de nomes:** uma tool MCP cujo nome colida com uma tool de backend confiável é
  **descartada** (o backend vence) — evita sombreamento/duplicação. Em colisão de nome de
  *servidor* entre gerais e de domínio, o geral tem precedência (com aviso no log).
- **Conteúdo não-confiável:** tools MCP podem trazer conteúdo arbitrário (prompt injection),
  como a busca web. Não há tools destrutivas por padrão (blast radius limitado), mas **vetar
  quais servidores MCP habilitar é responsabilidade de quem configura**.

---

## Testes

Suíte do **servidor** (unit + integração), determinística e **offline** — o LLM nunca é
chamado (os testes de integração injetam um agente stubado).

```bash
pytest tests/                                    # tudo
pytest tests/test_api.py                         # só integração
pytest tests/test_math_tools.py::test_basic_operators
```

Cobre: tools (math incl. guarda de DoS, calendário, domínio restaurante), erros (sem
vazamento de detalhe), config/registry/prompts, o bundle `Domain`, MCP (load/merge/isolamento
de falha) e dedup de tools, conversão de schemas e compilação do grafo, o middleware de limite
de corpo, e os endpoints HTTP (health, CORS, validação 422, streaming SSE com `CUSTOM ui_hints`,
wrap de `RUN_ERROR`, filtro de `RAW`).

---

## Segurança

> **Autenticação é intencionalmente deixada de fora.** Este é um **projeto base** — auth e
> rate-limit devem ser implementados por quem o consome (atrás de um gateway/proxy ou
> adicionando middleware). **Não exponha publicamente sem auth.**

Mitigações implementadas:

- **Anti-XSS:** Markdown e componentes de UI escapam todo conteúdo do agente e sanitizam
  URLs (só http/https/mailto).
- **DoS de potência:** `math_tools` recusa `**` de magnitude descomunal (ex.: `9**9**9`).
- **Sem vazamento de erro:** o cliente recebe mensagens genéricas (`describe_error`); o
  detalhe vai só ao log (`error_hint`).
- **Limite de corpo:** `MaxBodySizeMiddleware` (ASGI, não bufferiza o SSE) recusa POST acima
  de `AG_UI_MAX_BODY_BYTES` (413).
- **MCP resiliente:** falha de um servidor é isolada (logada e pulada); tools MCP não podem
  sombrear tools de backend confiáveis (dedup de nomes). Ver [MCP](#mcp-model-context-protocol).
- Sem `eval/exec/subprocess`; `math` é AST-safe; `.env` é gitignored.

Limitações conhecidas (requerem auth/infra para produção, a cargo do consumidor): sem auth +
CORS `*` permite qualquer origem acionar o agente; `MemorySaver` é in-memory e ilimitado (por
`threadId`); `threadId` não tem isolamento; conteúdo de busca web/MCP é não-confiável (prompt
injection, com blast radius limitado — sem tools destrutivas e sem SSRF local).

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
