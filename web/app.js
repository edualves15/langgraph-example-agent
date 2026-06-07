// Demonstração oficial do protocolo AG-UI sobre um agente LangGraph.
// Usa o cliente oficial @ag-ui/client (HttpAgent + AgentSubscriber).
// Cada evento recebido é logado no painel e no console do navegador, com os
// nomes de campos canônicos (type em SCREAMING_SNAKE_CASE, campos em camelCase).
import { HttpAgent } from "https://esm.sh/@ag-ui/client@0.0.55";
import { renderMarkdown } from "./markdown.js";
import { SVG } from "./icons.js";
import { FRONTEND_TOOLS } from "./frontend-tools.js";
import { escapeHtml } from "./escape.js";

// Dicas de apresentação do estado, fornecidas pelo BACKEND em runtime via evento AG-UI
// `CUSTOM` (`name="ui_hints"`) — o front não conhece o domínio. Default vazio ⇒ 100%
// genérico (rótulos humanizados / título "Resumo"). Ver onCustomEvent + renderSummary.
let stateTagIcons = {}; // { <subcampo>: <emoji> }
let stateTitles = {};   // { <fluxo>: <título> }

// Constantes — fonte única para valores que aparecem em múltiplos contextos.
const ACCENT_COLOR = "#6ea8fe";        // sincronizar com --accent em styles.css
const STATUS_LABELS = {
  idle: "idle", running: "running", waiting: "aguardando você", done: "done", error: "error",
};

// Cliente AG-UI 100% GENÉRICO: renderiza apenas com o que o protocolo fornece em
// runtime (eventos SSE). Não conhece nomes de ferramentas, regras de negócio nem o
// formato do estado/interrupt de um agente específico — funciona com qualquer backend
// AG-UI/LangGraph. A única "fronteira" com o back é o protocolo.

// O bundle ESM do @ag-ui/client desestrutura `fetch` de globalThis perdendo o
// vínculo com Window. Re-bind antes de qualquer uso da biblioteca.
globalThis.fetch = globalThis.fetch.bind(globalThis);

// ---------------------------------------------------------------------------
// Setup do agente oficial — aponta para o endpoint AG-UI exposto pelo FastAPI.
// ---------------------------------------------------------------------------
const agent = new HttpAgent({ url: "/agent" });

// ---------------------------------------------------------------------------
// Referências de DOM
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const chatEl = $("chat");
const logEl = $("log");
const toolsEl = $("tools");
const stateEl = $("state-list");
const statusEl = $("status");
const threadEl = $("thread");
const inputEl = $("input");
const sendBtn = $("send");
const approvalEl = $("approval");
const approvalText = $("approval-text");
const summaryEl = $("summary");
const summaryToggle = $("summary-toggle");
const summaryToggleLabel = $("summary-toggle-label");
const summaryCountEl = $("summary-count");

threadEl.textContent = "thread: " + agent.threadId;

// ---------------------------------------------------------------------------
// Frontend tools (ações client-side). O cliente é genérico: só itera o registry,
// anuncia os schemas ao agente e executa os handlers no navegador. Toda a lógica
// específica do app vive em frontend-tools.js.
// ---------------------------------------------------------------------------
const FT_BY_NAME = new Map(FRONTEND_TOOLS.map((t) => [t.name, t]));
const FT_SCHEMAS = FRONTEND_TOOLS.map(({ name, description, parameters }) => ({
  name,
  description,
  parameters,
}));
const executedToolCalls = new Set(); // toolCallId já executados no navegador
let latestMessages = [];             // mensagens reconstruídas (via onMessagesChanged)

// ---------------------------------------------------------------------------
// Estado preditivo (AG-UI PredictState) — GENÉRICO. O backend emite um CUSTOM
// "PredictState" com um mapeamento [{state_key, tool, tool_argument}]; enquanto os
// args dessa tool chegam (streaming), aplicamos `args[tool_argument]` à `state_key`
// de forma otimista, e o STATE_SNAPSHOT autoritativo reconcilia depois. Sem conhecer
// o negócio. (Se o provedor não faz streaming de args — ex.: Gemini — é no-op visível.)
// ---------------------------------------------------------------------------
let lastState = {};   // último estado autoritativo (snapshot/delta)
let predicted = {};   // overlay otimista (state_key -> valor)
let predictMap = [];  // mapeamento vindo do evento PredictState

function applyState() {
  const merged = { ...lastState, ...predicted };
  renderState(merged);
  renderSummary(merged);
}

// Aplica a previsão otimista: se `toolName` está no mapeamento, lê `tool_argument` dos
// args (parse tolerante a JSON parcial) e o aplica à `state_key`. Genérico.
function applyPredict(toolName, rawArgs) {
  if (!predictMap.length || !toolName) return;
  const entry = predictMap.find((p) => p.tool === toolName);
  if (!entry) return;
  let args = rawArgs;
  if (typeof args === "string") {
    try { args = JSON.parse(args); } catch { return; } // parcial/inválido → ignora
  }
  if (!args || typeof args !== "object" || !(entry.tool_argument in args)) return;
  predicted[entry.state_key] = args[entry.tool_argument];
  applyState();
}

// Cria um bloco INLINE no chat onde uma frontend tool renderiza seu componente
// interativo. Apresentado como mensagem do agente — rótulo "Agent (<duração>)",
// espelhando a bolha de agente concluída. A `message` (pergunta vinda do arg da tool) é
// renderizada ACIMA dos controles, no MESMO balão → uma única mensagem (texto + widget).
// Devolve o container (nó DOM) onde o handler monta o widget.
function createToolUiBlock(message) {
  const label = lastRunElapsed ? agentLabelHTML(lastRunElapsed) : "Agent";
  const wrapper = document.createElement("div");
  wrapper.className = "msg-wrapper assistant tool-ui";
  wrapper.innerHTML =
    `<div class="msg-header">` +
      `<span class="avatar" aria-hidden="true" style="display:none"></span>` +
      `<div class="who">${label}</div>` +
    `</div>` +
    `<div class="tool-ui-body bubble">` +
      (message ? `<div class="tool-ui-msg">${renderMarkdown(message)}</div>` : "") +
      `<div class="tool-ui-widget"></div>` +
    `</div>`;
  chatEl.appendChild(wrapper);
  // O widget é montado no container SÓ depois (dentro do handler). Rola após a montagem +
  // layout (duplo rAF) para mostrar o widget inteiro, não a altura antiga.
  requestAnimationFrame(() => requestAnimationFrame(scrollChatToBottom));
  return wrapper.querySelector(".tool-ui-widget");
}

function scrollChatToBottom() {
  chatEl.scrollTop = chatEl.scrollHeight;
}

// Colapsa o widget concluído num resumo de uma linha com chevron. Genérico — só esconde os
// controles (que já ficam disabled/muted) e oferece reexpandir. A escolha em si é ecoada no
// balão do usuário, então o resumo é enxuto.
function collapseToolUiWidget(container) {
  if (!container || !container.parentNode) return;
  container.classList.add("collapsed");
  const summary = document.createElement("button");
  summary.type = "button";
  summary.className = "uic-btn uic-btn--round uic-btn--neutral tool-ui-summary";
  summary.setAttribute("aria-label", "Mostrar ou ocultar");
  summary.innerHTML = `<span class="tog icon" aria-hidden="true">${SVG.chevron}</span>`;
  summary.addEventListener("click", () => {
    const collapsed = container.classList.toggle("collapsed");
    summary.classList.toggle("expanded", !collapsed);
  });
  // Ancora o botão INLINE logo após o último caractere do texto do agente (dentro do último
  // bloco do `.tool-ui-msg`); sem mensagem, cai antes do widget.
  const body = container.closest(".tool-ui-body");
  const msg = body && body.querySelector(".tool-ui-msg");
  if (msg) (msg.lastElementChild || msg).appendChild(summary);
  else container.parentNode.insertBefore(summary, container);
}

// Extrai um bloco cercado ```suggestions ... ``` da resposta do agente (recurso do chat, não
// uma tool). Tolerante a fence ainda ABERTO durante o streaming (some sem piscar). Devolve
// { body, suggestions } — body = texto sem o bloco; suggestions = uma por linha (sem -/*/aspas).
// Genérico: o front não conhece o domínio, só extrai uma lista de strings da resposta.
function splitSuggestions(raw) {
  const m = raw.match(/```\s*suggestions\b[\s\S]*?(?:```|$)/i);
  if (!m) return { body: raw, suggestions: [] };
  const inner = m[0]
    .replace(/```\s*suggestions\b/i, "")
    .replace(/```\s*$/, "");
  const suggestions = inner
    .split("\n")
    .map((s) => s.replace(/^[-*]\s*/, "").replace(/^["']|["']$/g, "").trim())
    .filter(Boolean);
  return { body: raw.slice(0, m.index).replace(/\s+$/, ""), suggestions };
}

// Renderiza as "próximas perguntas" como chips no slot de sugestões (acima do input).
// GENÉRICO: recebe uma lista de strings (extraídas da resposta) e cria botões `data-prompt`;
// o handler de clique já existente faz `send(prompt)`. Limpo no início de cada run.
function renderSuggestions(list) {
  const el = document.getElementById("suggestions");
  if (!el) return;
  el.innerHTML = "";
  for (const s of list || []) {
    if (s == null || String(s).trim() === "") continue;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "uic-btn uic-btn--pill uic-btn--neutral";
    b.dataset.prompt = String(s);
    b.textContent = String(s);
    el.appendChild(b);
  }
}

// Roda o agente anunciando as frontend tools e, sempre que ele chamar uma delas,
// renderiza o componente inline no chat, aguarda a interação do usuário, devolve o
// resultado como ToolMessage e roda de novo — até o agente parar de chamá-las (mesmo
// loop ReAct, fechado pelo cliente).
// Teto de iterações do loop de frontend tools — evita recursão sem fim caso o agente
// fique chamando tools indefinidamente (resiliência client-side).
const MAX_FT_ROUNDS = 25;

async function runWithFrontendTools(params, depth = 0) {
  await agent.runAgent({ ...params, tools: FT_SCHEMAS });

  const messages = latestMessages;
  const answered = new Set(
    messages.filter((m) => m.role === "tool").map((m) => m.toolCallId),
  );
  let executedAny = false;

  for (const m of messages) {
    const calls = m.toolCalls || m.tool_calls || [];
    for (const call of calls) {
      const name = call.function?.name || call.name;
      if (!FT_BY_NAME.has(name) || answered.has(call.id) || executedToolCalls.has(call.id)) {
        continue;
      }
      executedToolCalls.add(call.id);
      let args = call.function?.arguments ?? call.args ?? {};
      if (typeof args === "string") {
        try { args = JSON.parse(args); } catch { args = {}; }
      }
      const tool = FT_BY_NAME.get(name);

      let content, display;
      let container = null;
      try {
        setStatus("waiting");
        // `message` (genérico): a pergunta vai no balão, acima dos controles.
        const message = args?.message || args?.prompt || args?.title || "";
        container = createToolUiBlock(message);
        const res = await tool.handler(args || {}, { container });
        // Handler pode devolver { content, display } ou uma string crua (fallback).
        content = res && typeof res === "object" ? res.content : String(res);
        display = res && typeof res === "object" ? res.display : summarizeChoice(content);
        // Após a escolha, colapsa o widget num resumo (a escolha já vai no balão do usuário).
        collapseToolUiWidget(container);
      } catch (err) {
        content = "Erro ao executar a ferramenta no navegador: " + (err?.message || err);
        display = content;
      }
      addUserBubble(display);
      agent.addMessage({
        id: crypto.randomUUID(),
        role: "tool",
        content: String(content),
        toolCallId: call.id,
      });
      executedAny = true;
    }
  }

  if (executedAny) {
    if (depth + 1 >= MAX_FT_ROUNDS) {
      console.warn("[AG-UI] limite de rodadas de frontend tools atingido; interrompendo o loop.");
      return;
    }
    await runWithFrontendTools({ runId: crypto.randomUUID() }, depth + 1);
  }
}

// Estado de renderização (correlação por id, conforme o protocolo).
const assistantBubbles = new Map(); // messageId -> { el, body }
const toolCards = new Map();        // toolCallId -> { card, argsEl, resultEl, buffer }

// Coalescência do render de streaming: a cada delta marca a bolha como "suja" e agenda
// UM render por frame (requestAnimationFrame), em vez de re-renderizar o markdown inteiro
// a cada caractere (evita custo O(n²) em respostas longas; DOM final idêntico).
const dirtyBubbles = new Set();
let renderScheduled = false;
function scheduleBubbleRender(b) {
  dirtyBubbles.add(b);
  if (renderScheduled) return;
  renderScheduled = true;
  requestAnimationFrame(() => {
    renderScheduled = false;
    for (const bub of dirtyBubbles) {
      bub.body.innerHTML = renderMarkdown(splitSuggestions(bub.raw).body) + '<i class="blink"></i>';
    }
    dirtyBubbles.clear();
    chatEl.scrollTop = chatEl.scrollHeight;
  });
}

// ---------------------------------------------------------------------------
// Helpers de UI
// ---------------------------------------------------------------------------
function setStatus(s) {
  statusEl.textContent = STATUS_LABELS[s] || s;
  statusEl.className = "status mono " + s;
}

function addUserBubble(text) {
  const panel = chatEl.closest(".chat-panel");
  if (panel.classList.contains("is-empty")) {
    const chatStart = document.getElementById("chat-start");
    const composer = document.getElementById("composer");
    const suggestions = document.getElementById("suggestions");

    // Transição instantânea, sem animação — zero flick.
    chatStart.style.display = "none";
    panel.appendChild(composer);
    panel.insertBefore(suggestions, composer);
    panel.classList.remove("is-empty");
  }
  chatEl.appendChild(buildUserWrapper(text));
  chatEl.scrollTop = chatEl.scrollHeight;
}

function buildUserWrapper(text) {
  const wrapper = document.createElement("div");
  wrapper.className = "msg-wrapper user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = renderMarkdown(text);
  wrapper.appendChild(bubble);
  return wrapper;
}

// ── Bloco do agente ──

let pendingAgentBlock = null; // criado em RUN_STARTED, consumido no 1º TEXT_MESSAGE_START
let runBubble = null;         // bolha única do run atual (mostra só a mensagem final)
let runStartTime = null;
let runTimerInterval = null;
let currentAction = "pensando";
let lastRunElapsed = null;    // duração do último run finalizado (rótulo dos blocos pós-run)

function formatElapsed(ms) { return (ms / 1000).toFixed(1) + "s"; }

function timerLabel() {
  return "Working… (" + formatElapsed(Date.now() - runStartTime) + " · " + currentAction + ")";
}

function setAction(action) {
  currentAction = action;
}

function createAgentWrapper(statusClass, label, icon) {
  const wrapper = document.createElement("div");
  wrapper.className = "msg-wrapper assistant";
  const avatarHTML = statusClass === "spinner"
    ? `<span class="avatar" aria-hidden="true"><span class="dots"><i></i><i></i><i></i></span></span>`
    : `<span class="avatar avatar-${statusClass}" aria-hidden="true">${icon}</span>`;
  wrapper.innerHTML =
    `<div class="msg-header">` +
      avatarHTML +
      `<div class="who">${label}</div>` +
    `</div>` +
    `<div class="bubble streaming"></div>`;
  return { wrapper, bubble: wrapper.querySelector(".bubble"), raw: "" };
}

function setAgentStatus(wrapper, statusClass, label, icon) {
  const avatar = wrapper.querySelector(".avatar");
  avatar.className = "avatar" + (statusClass ? " avatar-" + statusClass : "");
  avatar.innerHTML = icon;
  avatar.style.display = icon ? "" : "none";
  wrapper.querySelector(".who").innerHTML = label;
}

// Rótulo do agente com o tempo de processamento em estilo muted e fonte menor.
// "Agent" normal + "(1.8s)" muted.
function agentLabelHTML(total) {
  return `Agent <span class="who-time">(${escapeHtml(total)})</span>`;
}

function getAssistantBubble(messageId) {
  let entry = assistantBubbles.get(messageId);
  if (!entry) {
    const block = createAgentWrapper("", "Agent", "");
    chatEl.appendChild(block.wrapper);
    entry = { el: block.bubble, body: block.bubble, wrapper: block.wrapper, raw: block.raw };
    assistantBubbles.set(messageId, entry);
  }
  return entry;
}

const LOG_CLASS = {
  RUN_STARTED: "lifecycle", RUN_FINISHED: "lifecycle", RUN_ERROR: "lifecycle",
  STEP_STARTED: "lifecycle", STEP_FINISHED: "lifecycle",
  TEXT_MESSAGE_START: "text", TEXT_MESSAGE_CONTENT: "text", TEXT_MESSAGE_END: "text",
  TOOL_CALL_START: "tool", TOOL_CALL_ARGS: "tool", TOOL_CALL_END: "tool", TOOL_CALL_RESULT: "tool",
  STATE_SNAPSHOT: "state", STATE_DELTA: "state", MESSAGES_SNAPSHOT: "state",
  CUSTOM: "custom", RAW: "custom",
};

function logEvent(event) {
  const line = document.createElement("div");
  line.className = "line";
  const cls = LOG_CLASS[event.type] || "other";
  const { type, ...rest } = event;
  line.innerHTML =
    `<span class="etype ${cls}">${escapeHtml(String(type))}</span> ` +
    `<span class="payload">${escapeHtml(JSON.stringify(rest))}</span>`;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
  bumpBadge("events");
  // Console do navegador — para verificação do SSE/protocolo.
  console.log("%c[AG-UI] " + type, "color:" + ACCENT_COLOR, event);
}

// Extrai um texto legível do resultado de uma frontend tool (JSON ou string).
// Ex.: '{"value":"Ver cardápio"}' → "Ver cardápio", '"O usuário confirmou."' → "Confirmado".
function summarizeChoice(raw) {
  if (!raw) return "";
  try {
    const obj = JSON.parse(raw);
    if (obj && typeof obj === "object") {
      for (const k of ["value", "selected", "result", "choice"]) {
        if (obj[k] != null && obj[k] !== "") {
          const v = obj[k];
          return Array.isArray(v) ? v.join(", ") : String(v);
        }
      }
      return Object.values(obj).join(", ") || raw;
    }
  } catch {}
  return raw;
}

// Chaves que o protocolo AG-UI/LangGraph sempre injeta no STATE_SNAPSHOT
// (conversa e tools de frontend). Não são "estado de negócio" — ficam fora do painel.
const PROTOCOL_STATE_KEYS = new Set(["messages", "tools"]);

// Renderiza GENERICAMENTE o estado compartilhado: cada chave (exceto as protocolares)
// como chave → valor. Sem conhecer nenhum agente específico — funciona com qualquer
// shape de estado vindo do STATE_SNAPSHOT.
function renderState(state) {
  stateEl.innerHTML = "";
  const keys = state && typeof state === "object"
    ? Object.keys(state).filter((k) => !PROTOCOL_STATE_KEYS.has(k))
    : [];
  if (keys.length === 0) {
    stateEl.innerHTML = `<div class="tab-empty">Nenhum estado compartilhado</div>`;
    return;
  }
  // Badge reflete o número real de chaves de estado (não acumula snapshots)
  setBadge("state", keys.length);
  for (const k of keys) {
    const v = state[k];
    const card = document.createElement("div");
    card.className = "state-card";

    // Header com toggle (accordion)
    const typeLabel = Array.isArray(v) ? "array[" + v.length + "]" : v && typeof v === "object" ? "object" : typeof v;
    card.innerHTML =
      `<div class="s-head" role="button" tabindex="0">` +
        `<span class="tog">▼</span>` +
        `<span class="s-key mono">${escapeHtml(k)}</span>` +
        `<span class="s-type">${typeLabel}</span>` +
      `</div>` +
      `<div class="s-body"></div>`;

    const body = card.querySelector(".s-body");
    // Sempre JSON — apresentação técnica e padronizada com tool calls
    const pre = document.createElement("pre");
    pre.className = "pre-block";
    pre.textContent = JSON.stringify(v, null, 2);
    body.appendChild(pre);

    // Accordion toggle
    card.querySelector(".s-head").addEventListener("click", () => {
      card.classList.toggle("collapsed");
      const tog = card.querySelector(".tog");
      if (tog) tog.textContent = card.classList.contains("collapsed") ? "▶" : "▼";
    });

    stateEl.appendChild(card);
  }
}

// Resumo legível e GENÉRICO de um valor (sem shape conhecido). Arrays/objetos preferem
// campos de nome comuns (mesma convenção genérica de cardList); senão juntam os valores.
function summarizeValue(v) {
  if (v == null || v === "") return "";
  if (Array.isArray(v)) return v.map(summarizeValue).filter(Boolean).join(", ");
  if (typeof v === "object") {
    for (const k of ["name", "title", "label", "id", "value"]) {
      if (v[k] != null && v[k] !== "") return summarizeValue(v[k]);
    }
    return Object.values(v).map(summarizeValue).filter(Boolean).join(", ");
  }
  return String(v);
}

// Formatação GENÉRICA de texto de chip: data ISO (YYYY-MM-DD) vira DD/MM; resto passa direto.
function prettyTagText(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  return m ? `${m[3]}/${m[2]}` : text;
}

// Edição GENÉRICA do estado compartilhado (AG-UI bidirecional): clona o estado autoritativo,
// aplica `mutator`, escreve em `agent.state` (vai em RunAgentInput.state no próximo run, lido
// pelo agente no próximo turno) e re-renderiza otimisticamente. Sem conhecer o domínio — só
// operações estruturais (remover item de array / limpar chave).
function editState(mutator) {
  const next = structuredClone(lastState && typeof lastState === "object" ? lastState : {});
  mutator(next);
  lastState = next;
  if (typeof agent.setState === "function") agent.setState(next);
  else agent.state = next;
  predicted = {};
  applyState();
}

// Popover "Sua reserva/Seu pedido" acionado por um botão no header do chat — revisar e EDITAR.
// O estado tem um objeto por FLUXO (`reservation`/`delivery`), padronizado `{ items, ...campos }`;
// só o ATIVO (objeto não-vazio) é mostrado. Renderiza uniformemente os subcampos do fluxo ativo:
// subcampo array (`items`) → uma linha por item (× remove o item); subcampo escalar → uma linha
// (× limpa o campo). Ícone por subcampo via `stateTagIcons`; título via `stateTitles` (mapas
// fornecidos pelo backend em runtime via CUSTOM/ui_hints). O botão/popover somem quando não há
// fluxo ativo.
function renderSummary(state) {
  const keys = state && typeof state === "object"
    ? Object.keys(state).filter((k) => !PROTOCOL_STATE_KEYS.has(k))
    : [];
  // Fluxo ativo = primeira chave de topo cujo valor é um objeto não-vazio.
  const flow = keys.find((k) => {
    const v = state[k];
    return v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length > 0;
  });

  const rows = []; // { key, text, remove }
  if (flow) {
    for (const [sk, sv] of Object.entries(state[flow])) {
      if (sv == null || sv === "" || (Array.isArray(sv) && sv.length === 0)) continue;
      if (Array.isArray(sv)) {
        sv.forEach((item, i) => {
          const text = summarizeValue(item);
          if (!text) return;
          rows.push({
            key: sk, text,
            remove: () => editState((s) => { if (Array.isArray(s[flow]?.[sk])) s[flow][sk].splice(i, 1); }),
          });
        });
      } else {
        const text = summarizeValue(sv);
        if (text) rows.push({
          key: sk, text,
          remove: () => editState((s) => { if (s[flow]) delete s[flow][sk]; }),
        });
      }
    }
  }

  if (rows.length === 0) {
    // Sem fluxo ativo: esconde o botão e fecha/esvazia o popover.
    summaryToggle.hidden = true;
    summaryToggle.setAttribute("aria-expanded", "false");
    summaryEl.hidden = true;
    summaryEl.innerHTML = "";
    return;
  }
  const title = stateTitles[flow] || "Resumo";
  summaryToggle.hidden = false;
  summaryToggleLabel.textContent = title;
  summaryCountEl.textContent = String(rows.length);
  summaryEl.innerHTML =
    `<div class="summary-pop-head">${escapeHtml(title)}</div>` +
    `<div class="summary-body"></div>`;
  const body = summaryEl.querySelector(".summary-body");
  for (const r of rows) {
    const row = document.createElement("div");
    row.className = "summary-row";
    const icon = stateTagIcons[r.key];
    const lead = icon
      ? `<span class="summary-icon">${escapeHtml(icon)}</span>`
      : `<span class="summary-key">${escapeHtml(humanizeLabel(r.key))}</span>`;
    row.innerHTML = lead + `<span class="summary-val">${escapeHtml(prettyTagText(r.text))}</span>`;
    const x = document.createElement("button");
    x.type = "button";
    x.className = "uic-btn uic-btn--round uic-btn--sm summary-x";
    x.setAttribute("aria-label", "Remover");
    x.textContent = "×";
    // stopPropagation: editar re-renderiza o popover (o × é destacado do DOM); sem isso o
    // handler de clique-fora no document fecharia o popover. Mantém aberto após editar.
    x.addEventListener("click", (e) => { e.stopPropagation(); r.remove(); });
    row.appendChild(x);
    body.appendChild(row);
  }
}

// Abre/fecha o popover "Sua reserva". O clique no × (editar) re-renderiza e mantém aberto.
function toggleSummary(open) {
  const next = open ?? summaryEl.hidden;
  summaryEl.hidden = !next;
  summaryToggle.setAttribute("aria-expanded", next ? "true" : "false");
}
summaryToggle.addEventListener("click", (e) => { e.stopPropagation(); toggleSummary(); });
// Clique fora fecha o popover.
document.addEventListener("click", (e) => {
  if (summaryEl.hidden) return;
  if (!summaryEl.contains(e.target) && !summaryToggle.contains(e.target)) toggleSummary(false);
});

// Preenche o campo de argumentos de um tool card a partir de um valor cru
// (string JSON, objeto ou nulo). Mantém oculto quando não há argumentos ({}).
function setToolArgs(t, raw) {
  if (raw == null || raw === "" || t.argsShown) return;
  let obj = raw;
  if (typeof raw === "string") {
    const s = raw.trim();
    if (!s) return;
    try {
      obj = JSON.parse(s);
    } catch {
      // String não-JSON com conteúdo — exibe crua (stream parcial de um provider).
      t.argsField.hidden = false;
      t.argsEl.textContent = s;
      return;
    }
  }
  // Objeto vazio ({}) = ferramenta sem argumentos → não mostra o campo.
  if (obj && typeof obj === "object" && !Array.isArray(obj) && Object.keys(obj).length === 0) return;
  t.argsField.hidden = false;
  t.argsEl.textContent = JSON.stringify(obj, null, 2);
  t.argsShown = true;
}

// ---------------------------------------------------------------------------
// Subscriber oficial — um handler por categoria de evento AG-UI.
// ---------------------------------------------------------------------------
const subscriber = {
  // Catch-all: registra TODOS os eventos (log + console).
  onEvent: ({ event }) => logEvent(event),

  // Lifecycle
  onStepStartedEvent: () => {
    // Atividade genérica e legível no chat — o nome cru do step fica só no log de eventos.
    currentAction = "trabalhando";
  },
  onRunStartedEvent: () => {
    setStatus("running");
    // Sugestões do turno anterior somem ao iniciar um novo run.
    renderSuggestions([]);
    runStartTime = Date.now();
    currentAction = "trabalhando";
    const block = createAgentWrapper("spinner", "Working… (0.0s · " + currentAction + ")", "");
    chatEl.appendChild(block.wrapper);
    chatEl.scrollTop = chatEl.scrollHeight;
    pendingAgentBlock = block;
    runTimerInterval = setInterval(() => {
      if (pendingAgentBlock) pendingAgentBlock.wrapper.querySelector(".who").textContent = timerLabel();
    }, 100);
  },
  onRunFinishedEvent: () => {
    clearInterval(runTimerInterval);
    runTimerInterval = null;
    const total = formatElapsed(Date.now() - runStartTime);
    lastRunElapsed = total;
    runStartTime = null;
    if (runBubble) setAgentStatus(runBubble.wrapper, "", agentLabelHTML(total), "");
    if (pendingAgentBlock) {
      // Run sem texto (ex.: só tool calls): descarta o spinner pendente.
      pendingAgentBlock.wrapper.remove();
      pendingAgentBlock = null;
    }
    finalizeRun("done");
    runBubble = null;
    assistantBubbles.clear();
    predicted = {};
    predictMap = [];
  },
  onRunErrorEvent: ({ event }) => {
    clearInterval(runTimerInterval);
    runTimerInterval = null;
    runStartTime = null;
    if (pendingAgentBlock) {
      pendingAgentBlock.wrapper.remove();
      pendingAgentBlock = null;
    }
    finalizeRun("error");
    const b = runBubble || getAssistantBubble("error-" + Date.now());
    b.el.classList.remove("streaming");
    b.body.innerHTML = SVG.warning + " " + escapeHtml(event.message || "Erro na execução.");
    sendBtn.disabled = !inputEl.value.trim();
    runBubble = null;
    assistantBubbles.clear();
    predicted = {};
    predictMap = [];
  },

  // Mensagens de texto (streaming).
  // Uma interação AG-UI = um run (RUN_STARTED→RUN_FINISHED, mesmo runId) e pode
  // conter VÁRIAS mensagens (cada uma com seu messageId): um preâmbulo que acompanha
  // a tool call + a resposta final após o resultado. Mantemos UMA bolha por run e,
  // a cada nova mensagem, SUBSTITUÍMOS o conteúdo — assim a bolha converge para a
  // mensagem final (a AIMessage sem tool calls, antes do RUN_FINISHED), descartando
  // preâmbulos. O protocolo não marca "é a última"; a regra estrutural é substituir.
  onTextMessageStartEvent: ({ event }) => {
    currentAction = "escrevendo resposta";
    if (pendingAgentBlock) {
      // Promove o spinner do RUN_STARTED a bolha do run.
      runBubble = { el: pendingAgentBlock.bubble, body: pendingAgentBlock.bubble, wrapper: pendingAgentBlock.wrapper, raw: "" };
      pendingAgentBlock = null;
    } else if (!runBubble) {
      runBubble = getAssistantBubble(event.messageId);
    }
    // Nova mensagem assume a bolha: zera o conteúdo (descarta a anterior/preâmbulo).
    runBubble.raw = "";
    runBubble.body.innerHTML = "";
    runBubble.el.classList.add("streaming");
    assistantBubbles.set(event.messageId, runBubble);
  },
  onTextMessageContentEvent: ({ event }) => {
    const b = assistantBubbles.get(event.messageId) || runBubble;
    if (!b) return;
    b.raw += event.delta;
    // Esconde o bloco ```suggestions do texto exibido (inclusive durante o streaming).
    // Render coalescido por frame (ver scheduleBubbleRender) — evita custo O(n²).
    scheduleBubbleRender(b);
  },
  onTextMessageEndEvent: ({ event }) => {
    const b = assistantBubbles.get(event.messageId);
    if (b) {
      dirtyBubbles.delete(b); // cancela qualquer render pendente; o final é definitivo
      b.el.classList.remove("streaming");
      // Sugestões = recurso do chat: extraídas da resposta do agente e viram chips.
      const { body, suggestions } = splitSuggestions(b.raw);
      b.body.innerHTML = renderMarkdown(body);
      if (suggestions.length) renderSuggestions(suggestions);
    }
  },

  // Tool calls
  onToolCallStartEvent: ({ event }) => {
    // Atividade genérica no chat; o nome cru da tool fica no card lateral + log.
    currentAction = "usando ferramenta";
    // Dedup: durante o resume de HITL o backend reemite TOOL_CALL_START para o
    // mesmo tool_call_id (nova instância do agente com streamed_tool_call_ids vazio).
    // O card existente receberá o resultado quando TOOL_CALL_RESULT chegar.
    if (toolCards.has(event.toolCallId)) {
      bumpBadge("tools");
      return;
    }
    // O protocolo AG-UI não expõe "origem" da tool call — mostramos só o nome cru.
    const card = document.createElement("div");
    card.className = "tool-card collapsed";
    card.innerHTML =
      `<div class="t-head mono" role="button" tabindex="0">` +
        `<span class="tog">▶</span>` +
        `<span class="dot"></span>` +
        `<span class="tname">${escapeHtml(event.toolCallName)}</span>` +
        `<span class="tid">${escapeHtml(event.toolCallId.slice(0, 8))}</span>` +
      `</div>` +
      `<div class="t-body">` +
        `<div class="field args-field" hidden><span class="lbl">argumentos</span><pre class="args pre-block"></pre></div>` +
        `<div class="field result-field" hidden><span class="lbl">resultado</span><pre class="result pre-block"></pre></div>` +
      `</div>`;
    // Accordion toggle no header
    card.querySelector(".t-head").addEventListener("click", () => {
      card.classList.toggle("collapsed");
      const tog = card.querySelector(".tog");
      if (tog) tog.textContent = card.classList.contains("collapsed") ? "▶" : "▼";
    });
    if (toolsEl.querySelector(".tab-empty")) toolsEl.innerHTML = "";
    toolsEl.appendChild(card);
    bumpBadge("tools");
    toolCards.set(event.toolCallId, {
      card,
      argsEl: card.querySelector(".args"),
      argsField: card.querySelector(".args-field"),
      resultEl: card.querySelector(".result"),
      resultField: card.querySelector(".result-field"),
      buffer: "",
      argsShown: false,
    });
  },
  // Alguns providers (ex.: Gemini) não fazem streaming dos args como
  // TOOL_CALL_ARGS — eles chegam completos na mensagem reconstruída
  // (ver onMessagesChanged). Mantemos este handler para providers que streamam.
  onToolCallArgsEvent: ({ event }) => {
    const t = toolCards.get(event.toolCallId);
    if (!t || t.argsShown) return;
    t.buffer += event.delta;
    setToolArgs(t, t.buffer);
  },
  onToolCallEndEvent: ({ event }) => {
    currentAction = "escrevendo resposta";
    const t = toolCards.get(event.toolCallId);
    if (t) t.card.classList.add("done");
  },
  onToolCallResultEvent: ({ event }) => {
    const t = toolCards.get(event.toolCallId);
    if (!t) return;
    t.resultField.hidden = false;
    let content = event.content;
    try { content = JSON.stringify(JSON.parse(content), null, 2); } catch { /* texto simples */ }
    t.resultEl.textContent = content;
  },
  // Fonte autoritativa das mensagens reconstruídas (superfície documentada do
  // AgentSubscriber). Guardamos para o loop de frontend tools e preenchemos os args
  // de cada tool card (oficial, agnóstico de provider).
  onMessagesChanged: ({ messages }) => {
    if (!Array.isArray(messages)) return;
    latestMessages = messages;
    for (const m of messages) {
      const calls = m.toolCalls || m.tool_calls;
      if (!calls) continue;
      for (const call of calls) {
        const name = call.function?.name || call.name;
        const rawArgs = call.function?.arguments ?? call.args;
        const t = toolCards.get(call.id);
        if (t && !t.argsShown) setToolArgs(t, rawArgs);
        applyPredict(name, rawArgs); // estado preditivo (genérico)
      }
    }
  },

  // Estado compartilhado — autoritativo. Atualiza o estado base e descarta a previsão
  // (reconciliação): o snapshot/delta é a fonte de verdade.
  onStateSnapshotEvent: ({ event }) => {
    lastState = event.snapshot || {};
    predicted = {};
    applyState();
  },
  // onStateChanged dá o estado reconstruído (após snapshot OU delta) — fonte única.
  onStateChanged: ({ state }) => {
    lastState = state || {};
    predicted = {};
    applyState();
  },

  // CUSTOM: HITL (on_interrupt), estado preditivo (PredictState) e dicas de UI do domínio
  // (ui_hints — ícones/títulos do resumo, fornecidos pelo backend; tratados genericamente).
  onCustomEvent: ({ event }) => {
    if (event.name === "on_interrupt") {
      showApproval(event.value);
    } else if (event.name === "PredictState") {
      predictMap = Array.isArray(event.value) ? event.value : [];
    } else if (event.name === "ui_hints") {
      const v = event.value && typeof event.value === "object" ? event.value : {};
      stateTagIcons = v.state_tag_icons && typeof v.state_tag_icons === "object" ? v.state_tag_icons : {};
      stateTitles = v.state_titles && typeof v.state_titles === "object" ? v.state_titles : {};
      applyState(); // re-renderiza o resumo com os ícones/títulos recém-recebidos
    }
  },
};

agent.subscribe(subscriber);

function finalizeRun(status) {
  setStatus(status);
  for (const [, b] of assistantBubbles) b.el.classList.remove("streaming");
  sendBtn.disabled = !inputEl.value.trim();
}

// ---------------------------------------------------------------------------
// Human-in-the-loop — aprovação e retomada (Command(resume=...))
// ---------------------------------------------------------------------------
// Rótulo legível a partir de uma chave (camelCase/snake_case → "Title Case").
function humanizeLabel(key) {
  return String(key)
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (c) => c.toUpperCase());
}

// Renderização GENÉRICA e LEGÍVEL do interrupt (o protocolo passa `value` verbatim,
// app-defined): texto-guia em destaque + os demais campos como "Rótulo: valor". Sem
// conhecer nenhuma ação específica e sem despejar JSON.
function showApproval(value) {
  let v = value;
  if (typeof v === "string") {
    try { v = JSON.parse(v); } catch { /* mantém string */ }
  }
  approvalText.innerHTML = "";

  if (v && typeof v === "object" && !Array.isArray(v)) {
    const LEAD_KEYS = ["question", "message", "description", "prompt"];
    const leadKey = LEAD_KEYS.find((k) => v[k] != null && v[k] !== "");
    if (leadKey) {
      const p = document.createElement("p");
      p.className = "approval-lead";
      p.textContent = String(v[leadKey]);
      approvalText.appendChild(p);
    }
    const skip = new Set([leadKey, "action"]);
    const dl = document.createElement("dl");
    dl.className = "approval-details";
    for (const [k, val] of Object.entries(v)) {
      if (skip.has(k) || val == null || val === "") continue;
      const row = document.createElement("div");
      row.className = "approval-row";
      const dt = document.createElement("dt");
      dt.textContent = humanizeLabel(k);
      const dd = document.createElement("dd");
      dd.textContent = summarizeValue(val);
      row.appendChild(dt);
      row.appendChild(dd);
      dl.appendChild(row);
    }
    if (dl.children.length) approvalText.appendChild(dl);
    if (!leadKey && !dl.children.length) approvalText.textContent = "Confirmar ação?";
  } else {
    approvalText.textContent = v != null && v !== "" ? String(v) : "Confirmar ação?";
  }
  approvalEl.classList.remove("hidden");
}

async function resolveApproval(approved) {
  approvalEl.classList.add("hidden");
  setStatus("running");
  sendBtn.disabled = true;
  // Retoma a MESMA thread com um booleano (convenção genérica approve/reject).
  // O backend interpreta `command.resume` como quiser; a lib o repassa verbatim.
  await runWithFrontendTools({
    runId: crypto.randomUUID(),
    forwardedProps: { command: { resume: approved } },
  });
}

$("approve").addEventListener("click", () => resolveApproval(true));
$("reject").addEventListener("click", () => resolveApproval(false));

// ---------------------------------------------------------------------------
// Envio de mensagens
// ---------------------------------------------------------------------------
async function send(text) {
  if (!text.trim() || sendBtn.disabled) return;
  addUserBubble(text);
  setStatus("running");
  sendBtn.disabled = true;

  agent.addMessage({ id: crypto.randomUUID(), role: "user", content: text });
  try {
    await runWithFrontendTools({ runId: crypto.randomUUID() });
  } catch (err) {
    console.error(err);
    finalizeRun("error");
  }
}

// Auto-resize do textarea (max-height controlado pelo CSS — 6.5em no styles.css)
inputEl.addEventListener("input", () => {
  sendBtn.disabled = !inputEl.value.trim();
  inputEl.style.height = "auto";
  inputEl.style.height = inputEl.scrollHeight + "px";
});

// Enter = enviar, Shift+Enter = nova linha
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("composer").dispatchEvent(new Event("submit"));
  }
});

$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = "";
  inputEl.style.height = "auto"; // reseta altura
  send(text);
});

$("suggestions").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-prompt]");
  if (btn) send(btn.dataset.prompt);
});

// ── Botões da barra de eventos ──

const copyBtn = $("copy-log");
const toggleDetailChk = $("toggle-detail");

// Injeta SVGs em todos os elementos com data-icon (fonte única via atributo HTML).
function initIcons() {
  document.querySelectorAll("[data-icon]").forEach((el) => {
    const name = el.dataset.icon;
    if (!SVG[name]) return;
    let svg = SVG[name];
    const size = el.dataset.iconSize;
    // Valida antes de interpolar no SVG (innerHTML) — evita quebra de atributo/injeção.
    if (size && /^[\d.]+(px|em|rem|%|pt)?$/.test(size)) {
      svg = svg.replace(/width="[^"]+"/, `width="${size}"`)
               .replace(/height="[^"]+"/, `height="${size}"`);
    }
    el.innerHTML = svg;
  });
}
initIcons();

// Estado do modo compacto (só tipos, sem payload) — inicializa do checkbox no DOM.
let logCompact = !toggleDetailChk.checked;

// Copiar: extrai o texto de cada linha do log e copia para a área de transferência.
copyBtn.addEventListener("click", async (e) => {
  e.stopPropagation();
  const lines = Array.from(logEl.querySelectorAll(".line"), (el) => {
    const type = el.querySelector(".etype")?.textContent || "";
    // Respeita o modo visual: compacto = só tipo; detalhado = tipo + payload.
    if (logCompact) return type;
    const payload = el.querySelector(".payload")?.textContent || "";
    return payload ? `${type} ${payload}` : type;
  });
  if (lines.length === 0) return;
  try {
    await navigator.clipboard.writeText(lines.join("\n"));
  } catch {
    // Fallback para contextos sem Clipboard API.
    const ta = document.createElement("textarea");
    ta.value = lines.join("\n");
    ta.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  // Feedback visual: troca ícone por check durante 1 s.
  copyBtn.innerHTML = SVG.check;
  setTimeout(() => { copyBtn.innerHTML = SVG.copy; }, 1000);
});

// Checkbox "detalhes": controla se o payload é exibido ou não.
// Marcado = modo detalhado; desmarcado = compacto (só tipos).
toggleDetailChk.addEventListener("change", () => {
  logCompact = !toggleDetailChk.checked;
  logEl.classList.toggle("compact", logCompact);
});

$("clear-log").addEventListener("click", (e) => {
  e.stopPropagation();
  logEl.innerHTML = `<div class="tab-empty">Nenhum evento ocorrido</div>`;
  setBadge("events", 0);
});

// ---------------------------------------------------------------------------
// Abas do painel de debug + contadores totais (tool calls / eventos)
// ---------------------------------------------------------------------------
const tabsEl = document.querySelector(".tabs");
const counters = { state: 0, tools: 0, events: 0 };

function setActiveTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.toggle("active", c.dataset.tab === name));
}

// Contador total persistente (não zera ao trocar de aba).
function bumpBadge(name) {
  if (!(name in counters)) return;
  const badge = $("badge-" + name);
  if (!badge) return;
  counters[name] += 1;
  badge.textContent = String(counters[name]);
}
// Define valor absoluto (ex.: número de chaves de estado).
function setBadge(name, value) {
  if (!(name in counters)) return;
  const badge = $("badge-" + name);
  if (!badge) return;
  counters[name] = value;
  badge.textContent = String(value);
}

tabsEl.addEventListener("click", (e) => {
  const btn = e.target.closest(".tab");
  if (btn) setActiveTab(btn.dataset.tab);
});
