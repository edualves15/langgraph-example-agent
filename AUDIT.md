# Auditoria de arquitetura e segurança

Revisão crítica do projeto (engine LangGraph + protocolo AG-UI + FastAPI + Pydantic + MCP +
front estático) focada em: **desacoplamento**, **aderência aos padrões oficiais**,
**segurança**, **código inflado** e **customizações que poderiam ser nativas**.

## Metodologia

- Leitura manual de todo o backend (`app/`) e do front (`web/`).
- Três varreduras independentes (backend, frontend, segurança/MCP/testes).
- Verificação dos achados rodando a suíte (`pytest tests/`) e exercitando o boot.

## Veredito

**O projeto já está bem arquitetado, idiomático e seguro.** A separação de camadas é
genuína (o engine genérico nunca importa o domínio), as bibliotecas oficiais são usadas em
vez de reinventadas, e a postura de segurança é sólida. **Não há falha crítica de
segurança.** O que havia eram melhorias **menores** de robustez/idiomática e um **bug real
de empacotamento**. Todas as correções aplicadas estão abaixo; o que foi revisado e mantido
de propósito está documentado para não ser "corrigido" por engano depois.

## Pontos fortes confirmados

- **Camadas desacopladas.** `app/agent/` (engine ReAct) recebe um `Domain` por injeção e
  nunca importa `app/domain/`. `grep` por termos de negócio nas camadas genéricas volta
  vazio. Trocar de domínio = 1 import no `main.py`.
- **Padrões oficiais.** `RunAgentInput`/`EventEncoder`/`LangGraphAgent` oficiais (sem
  adaptador SSE caseiro); `StateGraph` custom **justificado** (distinguir tool de backend de
  tool de frontend, que o `ToolNode` do prebuilt não faz); `pydantic-settings` para config;
  lifespan oficial p/ recursos async; `langchain-mcp-adapters` para MCP.
- **Segurança.** Escape de HTML centralizado (`web/escape.js`); sanitização de URL no
  Markdown (bloqueia `javascript:`/`data:`, inclusive ofuscado); `math` AST-safe com guarda
  de bomba de potência; `MaxBodySizeMiddleware` (limite por `content-length` **e** streaming);
  saneamento de erro em duas camadas (`describe_error` p/ cliente, `error_hint` só no log);
  isolamento de falha por servidor MCP; regra CORS correta (credenciais só com origens
  explícitas, nunca com `*`). Sem `eval`/`exec`/`subprocess`/`pickle`.

## "Críticos" levantados e **refutados** na verificação

| Alegação | Veredito |
|---|---|
| Handler genérico de `Exception` engole o status do `HTTPException` (vira 500) | **Falso.** O `ExceptionMiddleware` interno do Starlette trata `HTTPException` **antes** do catch-all `Exception`; o status é preservado. (E o `/invoke` só levanta 500 mesmo.) |
| Bomba de recursão no avaliador de math via aninhamento profundo | **Falso.** O teto de 500 chars permite ~250 níveis, bem abaixo do limite de recursão (1000) do Python. |
| Tratamento de acentos de weekday frágil | **Falso.** Aliases com e sem acento já estão ambos hardcoded; funciona. |

## Correções aplicadas

### Robustez

1. **Fail-fast de `GEMINI_API_KEY`** — `app/main.py::_require_api_key()` no lifespan. Antes,
   o servidor subia e só falhava com 500 genérico na 1ª requisição; agora aborta o startup
   com mensagem clara. (`config.py` mantém default `""` p/ não quebrar import/testes.)
2. **Timeout por servidor MCP no startup** — `app/services/mcp_service.py` envolve
   `client.get_tools()` em `asyncio.wait_for(...)` (`AG_UI_MCP_STARTUP_TIMEOUT`, default 15s).
   Um servidor pendurado é logado e pulado, sem travar a inicialização.

### Empacotamento (bug real)

3. **`pip install -e .` estava quebrado.** O `pyproject.toml` não tinha `[build-system]` nem
   configuração de pacotes; a auto-descoberta do setuptools encontrava dois diretórios de
   topo (`app` e `web`) e abortava (*"Multiple top-level packages discovered in a
   flat-layout"*). Adicionados `[build-system]` e `[tool.setuptools.packages.find]`
   (`include = ["app*"]`) — só `app` é distribuível; `web/` (estáticos) e `tests/` ficam de
   fora. O comando documentado volta a funcionar.

### Idiomática

4. **`AgentInvokeResponse.interrupt`**: `Any | None` → `dict | None` (`app/schemas.py`),
   alinhado ao contrato HITL (o valor do interrupt é um objeto de rótulos) e a um OpenAPI
   mais preciso.
5. **TypedDict para o estado do domínio** (`app/domain/restaurant/state.py`):
   `ReservationDraft`/`DeliveryDraft`/`MenuItem` documentam a forma do rascunho.
6. **`_approved(decision: bool | dict)`** tipado (`app/domain/restaurant/tools.py`).

### Consistência de idioma (código EN / UI PT)

7. Strings de UI **em inglês que vazaram** no front genérico viraram português, mantendo
   identificadores/chaves/CSS em inglês (`web/app.js`): `STATUS_LABELS`
   (`idle/running/done/error` → `ocioso/executando/concluído/erro`), `"Working…"` →
   `"Trabalhando…"`, `"Agent"` → `"Agente"`. Convenção registrada no `CLAUDE.md`.

### Testes

8. Novos testes: fail-fast da `GEMINI_API_KEY` (`tests/test_config_misc.py`) e skip de
   servidor MCP que estoura o timeout (`tests/test_mcp_service.py`). Suíte: **62 passam**.

## Revisado e **mantido de propósito** (com justificativa)

- **`MultiServerMCPClient` por servidor** (não um único client com todos): **deliberado** —
  isola erro/timeout de um servidor dos demais. Trocar por um client único perderia esse
  isolamento. Comentado no código.
- **`_custom_openapi`** (ajuste do 200 do `/stream` p/ `text/event-stream`): já é defensivo
  (try/except). FastAPI não infere o content-type de resposta a partir do `StreamingResponse`
  sozinho, então o pós-ajuste continua necessário.
- **Duplicação aparente entre `/stream` e `/invoke`**: divergem de fato (um faz `yield` de
  evento `RUN_ERROR`, o outro `raise HTTPException`). Extrair um helper reduziria a clareza
  sem ganho real.
- **Renderer Markdown próprio** (`web/markdown.js`): reimplementação **justificada** — sem
  build step, anti-XSS controlado, streaming-friendly. Manter.
- **`get_local_tools()` (8 tools de calendário + math)**: capacidades **genéricas** de um
  projeto base, não inflam o domínio. Manter.

## Limitações conscientes (responsabilidade do consumidor)

Não são defeitos — são escolhas documentadas de um **projeto base**: **sem auth** e **CORS
`*`** por padrão; **`MemorySaver`** in-memory (só demo); `threadId` sem isolamento; tools MCP
trazem conteúdo não-confiável (prompt injection, blast radius limitado). Auth/autorização e
rate-limit ficam a cargo de quem consome a base, conforme combinado.
