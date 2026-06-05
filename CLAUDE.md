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

# Página de demonstração (chat AG-UI) — abrir no navegador
#   http://localhost:8000/

# Endpoint oficial AG-UI (POST, SSE). Body = RunAgentInput (campos camelCase).
# Nota: em PowerShell use aspas duplas escapadas: -d "{\"threadId\": \"...\"}"
curl -N -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"threadId":"t1","runId":"r1","state":{},"messages":[{"id":"m1","role":"user","content":"quanto é 15 * 4?"}],"tools":[],"context":[],"forwardedProps":{}}'
```

## Architecture

**Implementação oficial do protocolo AG-UI sobre LangGraph.** O FastAPI (`app/`)
expõe o agente via integração oficial `ag_ui_langgraph` e serve uma página de
demonstração estática (`web/`) que usa o cliente oficial `@ag-ui/client`.

Não há sistema de narração caseiro — o mapeamento LangGraph → eventos AG-UI é feito
inteiramente pela biblioteca oficial. **Nunca reintroduza adaptadores de SSE
customizados, `NarrationMeta`, nem endpoints `/chat` / `/chat/stream`.**

### Bibliotecas oficiais

| Componente | Pacote | Versão |
|---|---|---|
| Integração LangGraph → AG-UI | `ag-ui-langgraph[fastapi]` | 0.0.37 |
| Core do protocolo (`ag_ui.core`) | `ag-ui-protocol` | 0.1.19 |
| Cliente browser | `@ag-ui/client` (esm.sh, pinado) | 0.0.55 |

### Request flow

```
GET  /            →  web/index.html (StaticFiles, html=True)
POST /agent       →  LangGraphAgent.run(RunAgentInput) → SSE de eventos AG-UI
GET  /agent/health →  {"status":"ok","agent":{"name":"private-agent"}}
GET  /health      →  {"status":"ok"}
```

`app/main.py`: `build_graph()` → `LangGraphAgent(name=..., graph=...)`. O `POST /agent` é
definido manualmente, replicando `add_langgraph_fastapi_endpoint` com os **mesmos
primitivos oficiais** (`agent.clone().run(input)` + `EventEncoder`), mas com um **wrap fino
de erro**: em qualquer exceção, emite um `RunErrorEvent` (`code="agent_run_error"`) — o
evento **canônico** do protocolo para falhas — em vez de derrubar o SSE cru (ver **Erros**).
`GET /agent/health` (paridade) e `GET /health` são definidos à parte. O `StaticFiles` é
montado em `/` **por último** para não capturar
`/agent` e `/health`.

### LangGraph graph (`app/agent/graph.py`)

Usa o prebuilt oficial `create_react_agent` (loop ReAct agente↔ferramentas):

- `model` = `get_llm()` (Gemini).
- `prompt` = callable `_prompt(state)` que injeta o system prompt (via
  `get_system_prompt()`, ver **Prompts**) com a data de hoje.
- `state_schema` = `AgentState` (`app/agent/state.py`): estende o `AgentState` do
  prebuilt (`messages` + `add_messages`, `remaining_steps`) e adiciona `proverbs:
  list[str]` como **estado compartilhado** exposto à UI.
- `checkpointer` = `MemorySaver` (necessário para threads e human-in-the-loop).

### Eventos AG-UI (wire format — verificável no console/Network)

`type` em **SCREAMING_SNAKE_CASE**, campos em **camelCase**, SSE `text/event-stream`:

- Lifecycle: `RUN_STARTED` (`threadId`,`runId`), `RUN_FINISHED`, `RUN_ERROR`, `STEP_STARTED`/`STEP_FINISHED`.
- Texto: `TEXT_MESSAGE_START` (`messageId`,`role`), `TEXT_MESSAGE_CONTENT` (`delta`), `TEXT_MESSAGE_END`.
- Ferramentas: `TOOL_CALL_START` (`toolCallId`,`toolCallName`), `TOOL_CALL_ARGS` (`delta`), `TOOL_CALL_END`, `TOOL_CALL_RESULT` (`toolCallId`,`content`).
- Estado: `STATE_SNAPSHOT` (`snapshot`), `STATE_DELTA` (`delta` JSON Patch), `MESSAGES_SNAPSHOT`.
- Especiais: `CUSTOM` (`name`,`value`) — interrupts chegam como `name="on_interrupt"`; `RAW` (passthrough de eventos LangGraph).

### Frontend (`web/`)

Página estática servida pelo FastAPI, sem build step:

- **Desacoplamento TOTAL.** O front é um cliente AG-UI **100% genérico** — renderiza
  **apenas com o que o protocolo fornece em runtime** (eventos SSE via `@ag-ui/client`),
  sem build/imports compartilhados e **sem nenhum conhecimento de negócio** (nomes de
  tools, shape de estado/interrupt, sugestões). Funciona com **qualquer** backend
  AG-UI/LangGraph; a única fronteira é o protocolo. **Não reintroduza `agent-config.js`
  nem literais específicos do agente no front.** Consequências (informação perdida, por
  escolha): rótulos de atividade = `stepName`/`toolCallName` crus; tool cards **sem** badge
  de origem (o protocolo não expõe origem); **sem** sugestões.
- `index.html` — 4 painéis: chat, estado, tool calls, log de eventos AG-UI. Sem literais
  do agente (slot de sugestões vazio; painel de estado genérico).
- `app.js` — `new HttpAgent({ url: "/agent" })` + `agent.subscribe(subscriber)`.
  O subscriber implementa um handler por categoria (`onTextMessageContentEvent`,
  `onToolCallStartEvent`, `onStateSnapshotEvent`, `onCustomEvent`, …) e o catch-all
  `onEvent` loga cada evento no painel e no `console`.
  - **Estado genérico:** `renderState(snapshot)` mostra todas as chaves do `STATE_SNAPSHOT`
    **exceto** as protocolares `messages`/`tools` (`PROTOCOL_STATE_KEYS`) — chave→valor,
    sem conhecer o agente.
  - **HITL genérico:** o `value` do interrupt (verbatim, app-defined) é renderizado como
    JSON, com destaque para um campo textual se houver (`question`/`message`/`description`/
    `prompt`); approve/reject retoma com **booleano** (`command.resume: true|false`).
- `markdown.js` — renderizador Markdown próprio (sem libs), usado nos balões do agente.
  Subconjunto prático/robusto (~GFM): headings 1–6, bold/itálico/bold-itálico,
  strikethrough, code inline/fenced, blockquote (multilinha/aninhado), listas
  ordenadas/não-ordenadas/aninhadas, links, imagens, tabelas, hr, quebras. Escapa todo
  texto e sanitiza URLs (só http/https/mailto/relativas) — anti-XSS. API:
  `renderMarkdown(src, { correct })`; `correct` (default `LENIENT=true`) liga um pré-passo
  corretor de deslizes do agente (espaço após `#`, etc.). Passe `correct:false` para
  render estrito.
- `styles.css` — estilo dos painéis e dos elementos Markdown do balão.
- Envio: `agent.addMessage({id, role:"user", content})` + `agent.runAgent({runId})`.
- HITL: ao receber `CUSTOM`/`on_interrupt`, mostra modal; aprovar/rejeitar chama
  `agent.runAgent({ forwardedProps: { command: { resume: approved } } })` (booleano).
- **Uma bolha por `runId`.** Uma "interação" = um run (`RUN_STARTED`→`RUN_FINISHED`,
  mesmo `runId`) e pode conter VÁRIAS mensagens (cada uma com seu `messageId`): um
  preâmbulo junto da tool call + a resposta final após o resultado. O chat mantém **uma
  única bolha por run** e, a cada novo `TEXT_MESSAGE_START`, **substitui** o conteúdo —
  convergindo para a mensagem final e descartando preâmbulos (`runBubble` em `app.js`,
  resetado em `RUN_FINISHED`/`RUN_ERROR`). HITL atravessa dois runs → duas bolhas
  (correto: execuções separadas pela aprovação).

### Adding tools

1. Crie `app/tools/my_tool.py` com `@tool` do `langchain_core.tools`.
2. Registre em `app/registries/tool_registry.py` → `get_local_tools()`.

Não há metadados de narração — o streaming (`TOOL_CALL_*`) é automático.

- Estado compartilhado: uma tool muta o estado retornando
  `Command(update={"<chave>": ..., "messages": [ToolMessage(...)]})` (ver
  `add_proverb`/`set_proverbs` em `app/tools/agui_demo_tools.py`, com
  `InjectedState` / `InjectedToolCallId`).
- Human-in-the-loop: chame `interrupt(value)` (`langgraph.types`) dentro da própria
  tool de ação (ver `send_email`); a retomada vem por `Command(resume=...)`.

`web_search` / `web_extract` (Tavily) são carregadas apenas quando `TAVILY_API_KEY` está setada.

### LLM provider

`app/services/llm_service.py` — único ponto para trocar de provider. Atual: Gemini (`ChatGoogleGenerativeAI`).

### Prompts (`app/agent/prompts/`)

System prompt em **pasta**, copy separada do código:

- `system.md`: o texto. **Totalmente genérico** — papel, idioma, tom (sóbrio,
  profissional, sem emojis), formatação (Markdown quando ajuda) e segurança/limites.
  **Não cita capacidades nem ferramentas**: o "quando/como usar" de cada tool vive **só**
  na **docstring** da tool (superfície de prompt que o `create_react_agent` expõe ao modelo
  via tool-calling). Zero acoplamento prompt↔toolset.
- `__init__.py`: `get_system_prompt()` lê `system.md` (via `importlib.resources`) e injeta
  a data no sentinela `{{TODAY}}` por `str.replace` (**não** `str.format` — evita conflito
  com `{`/`}` e crases do Markdown). API consumida por `_prompt(state)` em `graph.py`.

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
Tavily (`web_search`/`web_extract`) usa `description=` para seguir o mesmo padrão. **Ao
adicionar/alterar uma tool, atualize a docstring** (não o `system.md`).

### Erros (resiliência)

`describe_error` nunca lança e converte exceções em mensagens curtas e seguras.

- `app/errors.py::describe_error(exc)`: classifica a exceção em mensagem **específica**
  (auth/401-403, cota/429, requisição/400, indisponibilidade/5xx, timeout, rede) ou
  **genérica com pista** (`Tipo: 1ª linha`) quando indeterminável.
- Handlers globais em `app/main.py`: `RequestValidationError` → 422 JSON limpo;
  `Exception` → 500 JSON com a mensagem de `describe_error`. Ambos logam uma linha.
  Cobrem erros **pré-stream**/validação.
- **Stream `/agent`** (wrap fino): o gerador envolve `agent.run()` em `try/except`; em erro
  loga **uma linha** (sem traceback) e emite um `RunErrorEvent`
  (`type=RUN_ERROR, code="agent_run_error"`) — evento **canônico** do protocolo — antes de
  fechar o stream. (A lib também emite `RUN_ERROR` para eventos `"error"` do LangGraph; o
  wrap cobre as exceções Python cruas que ela não trata.)

## Environment variables

Copy `.env.example` to `.env`. Required keys:

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — | Required (Gemini provider) |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Model name |
| `TAVILY_API_KEY` | — | Enables the Tavily tools (`tavily_search` / `tavily_extract`) |
| `AG_UI_STREAM_RAW_EVENTS` | `true` | When `false`, omits `RAW` events (LangChain callback passthrough) from the SSE stream |
