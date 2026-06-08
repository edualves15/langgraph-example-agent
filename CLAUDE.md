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

# Tests (server-only: unit + integração; rodam offline, sem chamar o LLM)
pytest tests/

# Single test
pytest tests/test_math_tools.py::test_basic_operators

# Health check
curl http://localhost:8000/health

# Página de demonstração (chat AG-UI) — abrir no navegador
#   http://localhost:8000/

# Endpoint oficial AG-UI (POST, SSE). Body = RunAgentInput (campos camelCase).
# Nota: em PowerShell use aspas duplas escapadas: -d "{\"threadId\": \"...\"}"
curl -N -X POST http://localhost:8000/agent/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"threadId":"t1","runId":"r1","state":{},"messages":[{"id":"m1","role":"user","content":"quanto é 15 * 4?"}],"tools":[],"context":[],"forwardedProps":{}}'

# Contrapartida síncrona (mesmo body): resultado final agregado em JSON (AgentInvokeResponse).
curl -X POST http://localhost:8000/agent/invoke \
  -H "Content-Type: application/json" \
  -d '{"threadId":"t1","runId":"r1","state":{},"messages":[{"id":"m1","role":"user","content":"quanto é 15 * 4?"}],"tools":[],"context":[],"forwardedProps":{}}'
```

## Architecture

**Implementação oficial do protocolo AG-UI sobre LangGraph.** O FastAPI (`app/`)
expõe o agente via integração oficial `ag_ui_langgraph` e serve uma página de
demonstração estática (`web/`) que usa o cliente oficial `@ag-ui/client`.

Não há sistema de narração caseiro — o mapeamento LangGraph → eventos AG-UI é feito
inteiramente pela biblioteca oficial. **Nunca reintroduza adaptadores de SSE
customizados, `NarrationMeta`, nem endpoints `/chat` / `/chat/stream`.**

#### Separação de camadas (regra central)

Negócio isolado de infraestrutura; cada camada conhece as outras só por contrato/protocolo:

- **Engine genérico** (`app/agent/`): grafo ReAct (LangGraph puro), recebe um `Domain` por
  injeção; **nunca importa o domínio**.
- **Contrato `Domain`** (`app/agent/domain.py`): dataclass com `tools`, `state_schema`,
  `prompt`, `predict_state`, `ui_hints`, `mcp_servers`.
- **Domínio plugável** (`app/domain/<nome>/`): o plug de negócio; hoje
  `app/domain/restaurant/` exporta `DOMAIN`. **Trocar de domínio = 1 import no `main.py`.**
- **Capabilities genéricas** (`app/tools/`, `app/registries/`, `app/services/`) +
  **adaptador AG-UI** (`app/routers/agent.py`) + **servidor** (`middleware`/`errors`/
  `config`): sem domínio.
- **Frontend** (`web/`): 100% genérico — recebe tools/estado/títulos do backend em runtime
  (eventos AG-UI). Ver **Frontend**.

Regra prática: `reservation`/`delivery`/`restaurant`/menu só em `app/domain/` (e no
raciocínio do agente); `grep` nas camadas genéricas deve voltar vazio (exceto comentários).

### Bibliotecas oficiais

| Componente | Pacote | Versão |
|---|---|---|
| Integração LangGraph → AG-UI | `ag-ui-langgraph[fastapi]` | 0.0.37 |
| Core do protocolo (`ag_ui.core`) | `ag-ui-protocol` | 0.1.19 |
| Cliente browser | `@ag-ui/client` (esm.sh, pinado) | 0.0.55 |

### Request flow

```
GET  /             →  web/index.html (StaticFiles, html=True)
POST /agent/stream →  LangGraphAgent.run(RunAgentInput) → SSE de eventos AG-UI
POST /agent/invoke →  LangGraphAgent.run(RunAgentInput) → JSON agregado (AgentInvokeResponse)
GET  /agent/health →  {"status":"ok","agent":{"name":"private-agent"}}
GET  /health       →  {"status":"ok"}
```

**Estrutura (FastAPI):** `app/main.py` é o **composition root** — cria o
`FastAPI(lifespan=...)`, chama `configure_middlewares(app)` e inclui os routers. É o **único**
lugar que conhece engine + domínio: importa `DOMAIN` (`from app.domain.restaurant import
DOMAIN`). **Lifespan** (padrão oficial p/ recursos async): une os servidores MCP gerais
(`general_mcp_servers()`, da raiz) com os do domínio (`DOMAIN.mcp_servers`) via
`merge_servers(...)`, carrega as tools (`get_mcp_tools(servers)`, com isolamento de falha por
servidor), faz `build_graph(DOMAIN, extra_tools=mcp_tools)`, guarda o agente em
**`app.state.agent`** e as dicas de UI do domínio em **`app.state.ui_hints`**
(`DOMAIN.ui_hints`, entregues ao front pelo router do agente).

- `app/routers/agent.py` (`APIRouter`): **duas rotas para o mesmo agente** + health.
  - `POST /agent/stream` (SSE, superfície **canônica**): replica os **primitivos oficiais**
    (`request.app.state.agent.clone().run(input)` + `EventEncoder`) com um **wrap fino de erro**
    — em qualquer exceção emite `RunErrorEvent` (`code="agent_run_error"`), evento canônico do
    protocolo, em vez de derrubar o SSE (ver **Erros**). Logo após o primeiro `RUN_STARTED`,
    emite **um `CustomEvent` `name="ui_hints"`** com `app.state.ui_hints` (canal oficial AG-UI,
    sem HTTP paralelo) — o front genérico aplica os ícones/títulos do resumo de estado. Não
    emite nada se `ui_hints` for vazio.
  - `POST /agent/invoke` (JSON, **síncrono**): contrapartida não-streaming — roda o mesmo
    `clone().run(input)` e **agrega** os eventos num `AgentInvokeResponse`: `content` = a
    **mensagem final** do assistente (cada `TEXT_MESSAGE_START` reinicia o acúmulo → converge
    p/ a última, descartando preâmbulos; espelha "uma bolha por run" do front), `state` = último
    `STATE_SNAPSHOT` sem chaves protocolares (`_PROTOCOL_STATE_KEYS = {messages, tools}`),
    `interrupt` = `value` de um `CUSTOM` `on_interrupt` (HITL) ou `null`. Um `RUN_ERROR` (evento)
    ou qualquer exceção viram **500** (`ErrorResponse`, mensagem saneada por `describe_error`).
    **Sem parse de suggestions** (o bloco ` ```suggestions ` vem cru no `content`; a extração é
    só no front). Não emite `ui_hints` (canal de UI, irrelevante p/ consumidor JSON).
  - `GET /agent/health`.
- `app/routers/health.py` (`APIRouter`): `GET /health`.
- **DTOs & OpenAPI** (`app/schemas.py`): respostas tipadas com Pydantic — `ErrorResponse`,
  `HealthResponse`, `AgentInfo`, `AgentHealthResponse`, `AgentInvokeResponse` (camada de
  servidor, genérica). Health e `/agent/invoke` usam `response_model`; `/agent/stream` documenta
  `responses` (200 `text/event-stream` + 413/422/500 `ErrorResponse`) e acessa o agente via
  helper **tipado** `get_agent(request)`. **Contrato do agente (híbrido):** o **input** (ambas
  as rotas) é tipado pelo modelo oficial `RunAgentInput` (`Body(...)` com exemplo) → aparece no
  *Schemas* com seus aninhados; o **output** do `/agent/stream` é SSE (não modelável como corpo
  único) → documentado como **catálogo de eventos** no 200 + referência à spec/pacote AG-UI; o
  do `/agent/invoke` é o `AgentInvokeResponse` (JSON nativo). O `app.openapi` (`_custom_openapi`
  em `main.py`) faz só um ajuste mínimo: deixar o 200 do `/agent/stream` como `text/event-stream`
  (remove o `application/json` que o FastAPI mescla). `/docs`,`/redoc`,`/openapi.json` ligáveis
  por `APP_ENABLE_DOCS` (`_docs_kwargs`).
- `app/middleware.py` (`configure_middlewares`): **CORS** (`CORSMiddleware`) — permite que
  qualquer frontend AG-UI de outra origem consuma o agente. Origens via `AG_UI_CORS_ORIGINS`
  (default `*`); conforme a spec, credenciais só ligam com origens explícitas (wildcard `*` é
  incompatível com `allow_credentials=True`).
- Os `@app.exception_handler` (validação/Exception) ficam em `main.py`. O `StaticFiles` é
  montado em `/` **por último** para não capturar `/agent/*`/`/health`.
- **MCP** (`app/services/mcp_service.py`): scaffold oficial via `MultiServerMCPClient`
  (`langchain-mcp-adapters`). **Duas origens** de servidores (convenção `mcpServers`),
  unidas no lifespan: **gerais** (`mcp.json` na raiz, capabilities sem domínio) e **de
  domínio** (`app/domain/<dominio>/mcp.json` → `Domain.mcp_servers`, viajam com o plug).
  Ambas **vazias** por padrão → `get_mcp_tools()` retorna `[]`. Funções: `load_mcp_servers(path)`,
  `general_mcp_servers()`, `merge_servers(*dicts)` (colisão de nome de servidor → 1º vence,
  com aviso) e `get_mcp_tools(servers)` (**isola falha por servidor**: um servidor com erro é
  logado e pulado, não derruba o startup). As tools entram no grafo por
  `build_graph(DOMAIN, extra_tools=...)`, que **deduplica nomes** (backend confiável vence).

### LangGraph graph (`app/agent/graph.py`)

`StateGraph` custom (loop ReAct), **não** o prebuilt `create_react_agent` — porque o
`ToolNode` do prebuilt executaria **toda** tool call, e precisamos distinguir tools de
**backend** (executadas no servidor) de tools de **frontend** (anunciadas pelo cliente
em runtime e executadas no navegador). Estrutura:

`build_graph(domain: Domain, extra_tools=None)` é **genérico/injetado** — recebe o `Domain`
(ver `app/agent/domain.py`) e nunca importa o negócio. Estrutura:

- Tools de backend = `_merge_backend_tools([*get_local_tools(), *domain.tools], extra_tools)`:
  genéricas + domínio (autoritativas) + `extra_tools` (MCP), com **dedup de nomes** — uma tool
  externa/MCP colidente é descartada e logada (o backend confiável vence; protege contra
  sombreamento, ex.: um MCP expondo `create_reservation`).
- Nó `agent` (async): monta `_prompt(state, domain.prompt)` (system prompt genérico +
  fragmento do domínio + `messages`) e vincula ao LLM **as tools de backend + os schemas das
  tools de frontend**. Estes vêm de `state["tools"]` (a lib `ag_ui_langgraph` escreve ali as
  tools do
  `RunAgentInput.tools`), convertidos por `_frontend_tool_schemas(...)` para
  `{"type":"function","function":{...}}` — excluindo nomes que colidam com tools de
  backend (o backend vence).
- Roteamento (`route`): sem `tool_calls` → `END`; se **toda** chamada for de tool de
  backend → nó `tools` (`ToolNode`, executa no servidor); se houver chamada a tool de
  frontend → `END` (a lib já emitiu `TOOL_CALL_*`; o navegador executa e retoma com um
  `ToolMessage` no run seguinte). Assume 1 tool call por passo (padrão do Gemini).
- `model` = `get_llm()` (Gemini); `prompt` via `_prompt(state, domain.prompt)`
  (`get_system_prompt(domain_fragment)` com a data de hoje, ver **Prompts**).
- `predict_state` (metadata) vem de `domain.predict_state` (hoje `[]`).
- `state_schema` = `domain.state_schema`: subclasse de `AgentState` (`app/agent/state.py`,
  que herda `messages`/`remaining_steps` do prebuilt e declara `tools: list[dict]`)
  estendida pelo domínio com suas chaves (ex.: `RestaurantState`: `reservation`/`delivery`).
- `checkpointer` = `MemorySaver` (necessário para threads e human-in-the-loop).

### Eventos AG-UI (wire format — verificável no console/Network)

`type` em **SCREAMING_SNAKE_CASE**, campos em **camelCase**, SSE `text/event-stream`:

- Lifecycle: `RUN_STARTED` (`threadId`,`runId`), `RUN_FINISHED`, `RUN_ERROR`, `STEP_STARTED`/`STEP_FINISHED`.
- Texto: `TEXT_MESSAGE_START` (`messageId`,`role`), `TEXT_MESSAGE_CONTENT` (`delta`), `TEXT_MESSAGE_END`.
- Ferramentas: `TOOL_CALL_START` (`toolCallId`,`toolCallName`), `TOOL_CALL_ARGS` (`delta`), `TOOL_CALL_END`, `TOOL_CALL_RESULT` (`toolCallId`,`content`).
- Estado: `STATE_SNAPSHOT` (`snapshot`), `STATE_DELTA` (`delta` JSON Patch), `MESSAGES_SNAPSHOT`.
- Especiais: `CUSTOM` (`name`,`value`) — interrupts chegam como `name="on_interrupt"`; estado preditivo como `name="PredictState"` (`value`=mapeamento `[{state_key,tool,tool_argument}]`); dicas de UI do domínio como `name="ui_hints"` (`value`=`{state_tag_icons, state_titles}`, emitido pelo router após o `RUN_STARTED`); `RAW` (passthrough de eventos LangGraph).

### Frontend (`web/`)

Página estática servida pelo FastAPI, sem build step:

- **Cliente genérico + tools de UI genéricas.** `app.js` é um cliente AG-UI **genérico**
  — renderiza **apenas com o que o protocolo fornece em runtime** (eventos SSE via
  `@ag-ui/client`) e **não conhece nomes de tools, shape de estado/interrupt nem
  sugestões**. As tools de frontend (`frontend-tools.js`) e os widgets (`ui-components.js`)
  são **agnósticos de domínio**: `app.js` apenas itera o registry. **O domínio (hoje,
  Restaurante) vive só no BACKEND** + no raciocínio do agente. Se `FRONTEND_TOOLS = []`,
  `app.js` volta a ser 100% genérico. Consequências (por escolha): tool cards **sem** badge
  de origem; **sem** sugestões. **No chat**, os rótulos de atividade são genéricos e legíveis
  (`trabalhando`/`usando ferramenta`; cabeçalho final `Agent (Xs)`) — o nome cru do
  `stepName`/`toolCallName` fica só na aba "Tool calls" e no log de eventos, não acima das
  bolhas.
- `ui-components.js` — toolkit de **widgets genéricos** (sem negócio): `optionList`
  (checkboxes/radios), `cardList` (cards selecionáveis), `buttonGroup` (botões de resposta
  rápida — um toque responde, sem confirmar; cada botão `{label, value, kind}`, `kind` ∈
  primary/neutral/danger/success saneado contra whitelist, **default `neutral`**),
  `numberStepper` (seletor de número −/+ com confirmar; `{title,min,max,step,value}`, input
  editável), `confirmDialog` (Sim/Não). Cada um renderiza num `container` e devolve uma
  `Promise` que resolve na interação do usuário. **Botões unificados**: todos usam a classe
  canônica `.uic-btn` (+ `--kind`) — base **sutil** (superfície + hairline), só `--primary` é
  preenchido em accent (a única ação de destaque); estados `disabled`/`chosen` distintos, com
  **✓ padronizado** (badge circular accent, igual ao de card selecionado). **Opções são
  CONTROLES, não botões**: lista vertical compacta (largura do conteúdo, à esquerda) com
  radio (ponto) / checkbox (✓) custom (`appearance:none`). **Layout sem esticar**: cards em
  grid `auto-fill` com largura limitada empacotado à esquerda; respostas rápidas do tamanho
  do conteúdo. Anti-XSS (escapa todo texto). **Sem moeda hardcoded**: `cardList`/`present_cards`
  aceitam um `currency` (ISO 4217) opcional em runtime para formatar preços; sem ele, o preço
  é renderizado cru (número ou string passthrough). **`optionList`/`cardList`** mantêm o
  "Confirmar" **desabilitado** (mutado) até haver ≥1 seleção válida — impede envio vazio.
- `frontend-tools.js` — **tools de UI genéricas** anunciadas ao agente: `present_cards`,
  `present_options`, `present_buttons` (botões de resposta rápida de um toque),
  `present_number` (seletor de número/quantidade), `confirm_dialog`
  (`{ name, description, parameters, handler }`). O
  `handler(args, { container })` compõe um widget de `ui-components.js`, **aguarda** a
  interação e retorna **`{ content, display }`**: `content` vira o `ToolMessage` (vai ao
  agente); `display` é o texto **amigável** do balão do usuário (rótulos — título do card,
  label do botão, etc. — não ids/valores crus). Toda tool tem um arg **`message`** (a
  pergunta), renderizado pelo `app.js` **acima** dos controles, no mesmo balão.
  Renderizadas **inline no chat**. Após a escolha, o `app.js` **colapsa** o widget num resumo
  de uma linha (`✓ Respondido` + chevron). Ver https://docs.ag-ui.com/concepts/tools.
- `index.html` — painel de chat + lateral (abas estado/tool calls/eventos). Sem literais do
  agente (slot de sugestões vazio; painel de estado genérico). Os componentes interativos
  são montados inline no chat (não há painel lateral de frontend tools).
- `app.js` — `new HttpAgent({ url: "/agent/stream" })` + `agent.subscribe(subscriber)`.
  O subscriber implementa um handler por categoria (`onTextMessageContentEvent`,
  `onToolCallStartEvent`, `onStateSnapshotEvent`, `onCustomEvent`, …) e o catch-all
  `onEvent` loga cada evento no painel e no `console`.
  - **Tools de frontend:** `runWithFrontendTools(params)` envolve `agent.runAgent`,
    **anunciando** `FT_SCHEMAS` (`tools`) em todo run; ao terminar o run, varre as
    mensagens reconstruídas (`latestMessages`, capturadas em `onMessagesChanged` — superfície
    documentada do subscriber) por chamadas a tools do registry ainda sem `ToolMessage`,
    cria um **bloco inline no chat** (`createToolUiBlock(message)`), executa o
    `handler(args,{container})` (que **aguarda** a interação do usuário no componente), **colapsa**
    o widget num resumo (`collapseToolUiWidget`), ecoa a escolha num **balão do usuário**
    (`display`) e devolve o `content` via `agent.addMessage({role:"tool",...})` — **roda de novo**
    até o agente parar de chamá-las (fecha o loop ReAct no cliente). Status fica `waiting`
    enquanto aguarda.
    - **Widgets = PUROS CONTROLES; a pergunta vem do arg `message`.** Os widgets
      (`ui-components.js`) **não** renderizam texto. A pergunta/contexto vem do arg **`message`**
      da tool (reforçado no `system.md` e nas descrições) e o `createToolUiBlock(message)` a
      renderiza (markdown) **acima** dos controles, no mesmo balão → **uma mensagem só**
      (`Agent (Xs)` + pergunta + controles). Isso não depende de o modelo escrever prosa
      (robusto com flash-lite). O balão do usuário usa `display` (rótulos amigáveis), não o
      `content` técnico.
  - **Estado genérico:** `renderState(snapshot)` mostra todas as chaves do `STATE_SNAPSHOT`
    **exceto** as protocolares `messages`/`tools` (`PROTOCOL_STATE_KEYS`) — chave→valor,
    sem conhecer o agente. `renderSummary(snapshot)` rende as mesmas chaves num **popover de
    resumo** acionado por um **botão no header do chat** (`#summary-toggle` + `#summary`, com
    contador; some quando não há estado): array vira uma linha por elemento, objeto plano uma
    linha por subcampo, escalar uma linha (`summarizeValue` prefere `name/title/label/id`; datas
    ISO viram `DD/MM` por heurística genérica). O **ícone por chave** (`stateTagIcons`) e o
    **título** (`stateTitles`) vêm do **backend em runtime** via `CUSTOM`/`ui_hints` (não há
    mais ponto de domínio no front; defaults `{}` → sem ícone cai em rótulo humanizado, título
    em "Resumo"). Cada linha tem um **×** que **edita** o estado de forma estrutural genérica
    (remove item de array / limpa chave) via **estado bidirecional do AG-UI**: `editState` clona,
    muta, escreve em `agent.state`/`agent.setState` (vai em `RunAgentInput.state` no próximo run,
    lido pelo agente no próximo turno) e re-renderiza otimisticamente. Ambos (`renderState` +
    `renderSummary`) chamados em `applyState()`.
  - **Sugestões de próxima pergunta = recurso do chat (não-tool).** O agente termina a resposta
    com um bloco ` ```suggestions ` (uma sugestão por linha); `splitSuggestions(raw)` o extrai da
    resposta (escondendo-o do texto **inclusive durante o streaming**) e `renderSuggestions` cria
    chips `data-prompt` no slot `#suggestions` (acima do input; clicar faz `send`). Limpos em
    `RUN_STARTED`. **Sem tool, sem chamada LLM extra** (vêm no mesmo texto). Não há primitivo
    oficial AG-UI/LangGraph de sugestões (o CopilotKit faz com +1 chamada LLM); a convenção
    ` ```suggestions ` é genérica (o front só extrai uma lista de strings).
  - **HITL genérico e legível:** o `value` do interrupt (verbatim, app-defined) é
    renderizado de forma **legível** (não técnica) por `showApproval` — texto-guia em
    destaque (`question`/`message`/`description`/`prompt`) + os demais campos como linhas
    "Rótulo: valor" (rótulos humanizados; arrays juntados); **sem JSON**. Pula `action` e a
    chave-guia. approve/reject retoma com **booleano** (`command.resume: true|false`).
- `markdown.js` — renderizador Markdown próprio (sem libs), usado nos balões do agente.
  Subconjunto prático/robusto (~GFM): headings 1–6, bold/itálico/bold-itálico,
  strikethrough, code inline/fenced, blockquote (multilinha/aninhado), listas
  ordenadas/não-ordenadas/aninhadas, links, imagens, tabelas, hr, quebras. Escapa todo
  texto (via `escape.js` compartilhado) e sanitiza URLs (só http/https/mailto/relativas) —
  anti-XSS. API:
  `renderMarkdown(src, { correct })`; `correct` (default `LENIENT=true`) liga um pré-passo
  corretor de deslizes do agente (espaço após `#`, etc.). Passe `correct:false` para
  render estrito.
- `styles.css` — estilo dos painéis e dos elementos Markdown do balão. **Design flat:**
  cores sólidas + hairlines sólidas (1px), **sem degradês, sombras nem transparências**;
  hierarquia por tons de superfície (`--surface`/`--surface-hover`/`--surface-sel`); foco
  via `outline` sólido. Tipografia Inter + JetBrains Mono (links em `index.html`).
- Envio: `agent.addMessage({id, role:"user", content})` + `runWithFrontendTools({runId})`
  (que sempre anuncia `tools: FT_SCHEMAS`).
- HITL: ao receber `CUSTOM`/`on_interrupt`, mostra modal; aprovar/rejeitar chama
  `runWithFrontendTools({ forwardedProps: { command: { resume: approved } } })` (booleano).
- **Uma bolha por `runId`.** Uma "interação" = um run (`RUN_STARTED`→`RUN_FINISHED`,
  mesmo `runId`) e pode conter VÁRIAS mensagens (cada uma com seu `messageId`): um
  preâmbulo junto da tool call + a resposta final após o resultado. O chat mantém **uma
  única bolha por run** e, a cada novo `TEXT_MESSAGE_START`, **substitui** o conteúdo —
  convergindo para a mensagem final e descartando preâmbulos (`runBubble` em `app.js`,
  resetado em `RUN_FINISHED`/`RUN_ERROR`). HITL **e** tools de frontend atravessam dois
  runs → duas bolhas (correto: execuções separadas pela aprovação/execução no navegador).

### Adding tools

**Tool genérica (capability, sem domínio):**

1. Crie `app/tools/my_tool.py` com `@tool` do `langchain_core.tools`.
2. Registre em `app/registries/tool_registry.py` → `get_local_tools()`.

**Tool de domínio:** crie em `app/domain/<dominio>/tools.py` e registre na lista de tools
do `Domain` (ex.: `RESTAURANT_TOOLS` em `app/domain/restaurant/__init__.py`) — entra no grafo
via `Domain.tools`, **não** pelo registry genérico.

Não há metadados de narração — o streaming (`TOOL_CALL_*`) é automático. Ambas são
tools de **backend** (efeito/dado server-side, executadas no nó `tools`).

- **Domínio atual (Restaurante):** `app/domain/restaurant/tools.py` — `get_menu`,
  `get_available_times` (dados server-side), `update_reservation`/`update_delivery` (estado
  compartilhado) e `create_reservation`/`create_delivery_order`. O fragmento de prompt do
  domínio (`prompt.md`) instrui o agente a chamar a tool de atualizar (campos parciais)
  **logo após cada escolha** — pratos, data, horário, pessoas — para o painel refletir o
  **rascunho completo** ao vivo. A instrução de **preferir UI interativa** (tools de frontend)
  a texto livre é **genérica** (vive no `system.md`, sem nomear tools → o agente só usa o que
  veio no handshake).
- Human-in-the-loop: chame `interrupt(value)` (`langgraph.types`) dentro da própria
  tool de ação (ver `create_reservation`); a retomada vem por `Command(resume=...)` e o
  front mostra o modal `on_interrupt`. O `value` do interrupt deve ser **legível** (rótulos
  amigáveis, sem campos técnicos) — o front o renderiza como "Rótulo: valor". Ao **aprovar**,
  `create_reservation` retorna `Command(update={"reservation": {}, "delivery": {}, ...})`
  (precisa de `InjectedToolCallId`) — **zera os rascunhos** para o próximo fluxo começar
  limpo; ao **rejeitar**, retorna string (mantém o rascunho para ajuste).
- Estado compartilhado (agente-owned): uma tool muta o estado retornando
  `Command(update={"<chave>": ..., "messages": [ToolMessage(...)]})` com
  `InjectedState` / `InjectedToolCallId` (emite `STATE_SNAPSHOT`/`STATE_DELTA`; o front o
  renderiza genericamente no painel de estado). Exemplo: `update_reservation` muta
  `reservation` (`{items: [{name, price}], date, time, party_size, customer_name}`) —
  chave declarada em `RestaurantState` (`app/domain/restaurant/state.py`) — o rascunho.
- **Estado preditivo (`PredictState`):** o `agent_node` injeta `config.metadata.predict_state`
  de `domain.predict_state` (hoje `[]`). A lib emite o `CUSTOM PredictState`; o front (`app.js`,
  handler **genérico** `applyPredict`) aplica os args em streaming à `state_key` de forma
  otimista e reconcilia no `STATE_SNAPSHOT`. **Depende do provedor fazer streaming dos
  `TOOL_CALL_ARGS`** — com Gemini (args inteiros) é no-op, sem prejuízo (estado via snapshot).
- **Tool de frontend** (executada no **navegador**, não no back): NÃO crie `@tool` no
  back. As tools de UI genéricas já existem em `web/frontend-tools.js` (`present_cards`/
  `present_options`/`present_buttons`/`present_number`/`confirm_dialog`); o agente as usa passando os dados do
  domínio. Para
  um novo widget, adicione-o a `web/ui-components.js` e exponha uma tool em
  `frontend-tools.js`. O `app.js` anuncia em runtime e o grafo roteia de volta ao cliente.

### Trocar de domínio (plug)

1. Crie `app/domain/<novo>/` com: `tools.py` (`@tool`s de backend), `state.py` (subclasse de
   `AgentState` com as chaves do domínio), `prompt.md` (papel/fluxos), `ui_hints.py` (ícones/
   títulos do resumo), **`mcp.json` opcional** (servidores MCP do domínio; carregado por
   `load_mcp_servers(...)`) e `__init__.py` exportando `DOMAIN = Domain(name, tools,
   state_schema, prompt, predict_state, ui_hints, mcp_servers)`.
2. Em `app/main.py`, troque o import por `from app.domain.<novo> import DOMAIN`.

Engine, registry genérico, adaptador AG-UI e o front **não mudam**. As dicas de UI fluem ao
front pelo evento `CUSTOM`/`ui_hints`; sem `ui_hints`, o front fica 100% genérico.

Capacidades externas (ex.: busca web) **não** são embutidas — ficam a cargo do consumidor via
servidores MCP (`mcp.json` geral ou `Domain.mcp_servers`); ver **MCP**.

### LLM provider

`app/services/llm_service.py` — único ponto para trocar de provider. Atual: Gemini (`ChatGoogleGenerativeAI`).

### Prompts (`app/agent/prompts/`)

System prompt em **pasta**, copy separada do código:

- `system.md`: o texto **genérico** — papel (assistente virtual), idioma, tom (sóbrio,
  profissional, sem emojis), formatação (Markdown quando ajuda), segurança/limites e as
  **convenções AG-UI** genéricas (preferir UI interativa, pôr a pergunta no arg `message`,
  bloco ` ```suggestions `). **Não cita capacidades nem ferramentas de domínio**: o
  "quando/como usar" de cada tool vive **só** na **docstring** da tool. Zero acoplamento
  prompt↔toolset. **Sem negócio aqui** — o papel/fluxos do domínio vivem em
  `app/domain/<dominio>/prompt.md` (`Domain.prompt`).
- `__init__.py`: `get_system_prompt(domain_fragment="")` lê `system.md` (via
  `importlib.resources`), concatena o fragmento de domínio (`genérico + "\n\n" + fragment`) e
  injeta a data no sentinela `{{TODAY}}` por `str.replace` (**não** `str.format` — evita
  conflito com `{`/`}` e crases do Markdown). Consumida por `_prompt(state, domain.prompt)`
  em `graph.py`. Com `domain_fragment` vazio, o prompt fica 100% genérico.

### Docstrings das tools (padrão de prompt por-ferramenta)

A docstring (ou `description=`) de cada `@tool` é o que o modelo lê — invista nela. Padrão
único, em **inglês**:

```
<resumo de 1 linha>
Use this tool when: <gatilhos>.
Input:
- <arg> — <tipo, restrições>   (só args fornecidos pelo modelo; NÃO documente
                                 InjectedState/InjectedToolCallId)
Returns <forma do retorno>.   (+ "Good inputs:" / exemplos quando útil)
```
Tools sem docstring (ex.: vindas de MCP) devem trazer `description=` no mesmo padrão. **Ao
adicionar/alterar uma tool, atualize a docstring** (não o `system.md`).

### Erros (resiliência)

`describe_error` nunca lança e converte exceções em mensagens curtas e seguras.

- `app/errors.py::describe_error(exc)`: mensagem **segura para o cliente** — específica
  (auth/401-403, cota/429, requisição/400, indisponibilidade/5xx, timeout, rede) ou
  **genérica** quando indeterminável. **Não** expõe texto cru da exceção (evita
  info-disclosure num endpoint sem auth). A pista detalhada (`Tipo: 1ª linha`) vem de
  `error_hint(exc)` e é usada **só no log do servidor**.
- Handlers globais em `app/main.py`: `RequestValidationError` → 422 JSON limpo;
  `Exception` → 500 JSON com `describe_error` (cliente) + `error_hint` (log). Cobrem erros
  **pré-stream**/validação.
- **Stream `/agent/stream`** (wrap fino): o gerador envolve `agent.run()` em `try/except`; em erro
  loga **uma linha** (sem traceback) e emite um `RunErrorEvent`
  (`type=RUN_ERROR, code="agent_run_error"`) — evento **canônico** do protocolo — antes de
  fechar o stream. (A lib também emite `RUN_ERROR` para eventos `"error"` do LangGraph; o
  wrap cobre as exceções Python cruas que ela não trata.)
- **JSON `/agent/invoke`** (síncrono): mesmo agente, sem stream. Agrega os eventos do run e,
  em falha, responde **500** (`ErrorResponse`): um evento `RUN_ERROR` vira `HTTPException(500,
  message)`; exceção crua é logada (`error_hint`, só no log) e vira `HTTPException(500,
  describe_error(exc))` — cliente recebe mensagem genérica/segura. `CancelledError` (disconnect)
  aborta limpo.

## Segurança

Mitigações implementadas e limitações **conhecidas/aceitas**. **Auth fica de fora por
escolha**: este é um projeto **base** — autenticação/autorização e rate-limit são
responsabilidade de quem consome a base (gateway/proxy ou middleware próprio). Não expor
publicamente sem auth.

Implementado:
- **XSS:** escape de HTML compartilhado em **`web/escape.js`** (`escapeHtml`, escapa
  `&<>"`, fonte única importada por `app.js`/`ui-components.js`/`markdown.js`) — neutraliza
  conteúdo do agente em texto **e em atributos** (aspas). `markdown.js` sanitiza URLs (só
  http/https/mailto; bloqueia `javascript:`/`data:`, inclusive ofuscado) e escapa antes das
  regexes de link/imagem (título/alt já saem inertes). `initIcons` valida `data-icon-size`
  (`/^[\d.]+(px|em|rem|%|pt)?$/`) antes de interpolar no SVG.
- **DoS de potência:** `math_tools._guard_pow` recusa `**` cujo resultado teria magnitude
  descomunal (ex.: `9**9**9`), sem afetar matemática normal.
- **Info-disclosure:** erros ao cliente são genéricos (`describe_error`); detalhe só no log
  (`error_hint`).
- **Limite de corpo:** `MaxBodySizeMiddleware` (ASGI puro, não bufferiza o SSE) recusa POST
  acima de `AG_UI_MAX_BODY_BYTES` (413) — por `content-length` **e** contando bytes em
  streaming (cobre `transfer-encoding: chunked` sem header).
- **Resiliência do stream:** o gerador do `/agent/stream` trata `asyncio.CancelledError`
  (disconnect do cliente) abortando limpo sem emitir `RUN_ERROR` (o `/agent/invoke` também
  trata o `CancelledError`); o loop de frontend tools no `app.js` tem teto de rodadas
  (`MAX_FT_ROUNDS`) contra recursão sem fim.
- **MCP resiliente:** `get_mcp_tools` isola falha por servidor (um servidor com erro é logado
  e pulado, não derruba o startup); `_merge_backend_tools` impede que uma tool MCP sombreie/
  duplique uma tool de backend confiável (dedup por nome, backend vence).
- Sem `eval/exec/subprocess/pickle`; `math` é AST-safe; `.env` no `.gitignore`.

Limitações aceitas (precisam de auth/infra antes de produção, a cargo do consumidor):
- **Sem auth + CORS `*`** → qualquer origem aciona o agente (custo/abuso). Restrinja via
  `AG_UI_CORS_ORIGINS`; adicione auth/rate-limit ao consumir a base.
- **`MemorySaver`** é in-memory e ilimitado (cresce por `threadId`) — só demo.
- **`threadId` sem isolamento** (quem souber um, continua/lê a conversa).
- **Tools MCP** (se habilitadas) trazem conteúdo não-confiável (prompt injection); blast radius
  limitado (sem tools destrutivas por padrão). Vetar quais servidores habilitar é do consumidor.
  Vetar quais servidores MCP habilitar é responsabilidade de quem configura.
- **Chamadas mistas backend+frontend** numa mesma mensagem do modelo são caso de borda
  (assume-se 1 tool call por passo).

## Environment variables

Copy `.env.example` to `.env`. Required keys:

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — | Required (Gemini provider) |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Model name |
| `AG_UI_STREAM_RAW_EVENTS` | `true` | When `false`, omits `RAW` events (LangChain callback passthrough) from the SSE stream |
| `AG_UI_CORS_ORIGINS` | `*` | Origens permitidas via CORS (CSV). `*` libera todas; com origens explícitas, credenciais são habilitadas. |
| `AG_UI_MAX_BODY_BYTES` | `2000000` | Tamanho máximo do corpo de uma requisição (bytes). `0` desabilita o limite. |
| `APP_ENABLE_DOCS` | `true` | Quando `false`, desliga `/docs`, `/redoc` e `/openapi.json` (recomendado em produção). Config de APLICAÇÃO — sem prefixo `AG_UI_`. |
