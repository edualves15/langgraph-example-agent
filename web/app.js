// Demonstração oficial do protocolo AG-UI sobre um agente LangGraph.
// Usa o cliente oficial @ag-ui/client (HttpAgent + AgentSubscriber).
// Cada evento recebido é logado no painel e no console do navegador, com os
// nomes de campos canônicos (type em SCREAMING_SNAKE_CASE, campos em camelCase).
import { HttpAgent } from "https://esm.sh/@ag-ui/client@0.0.55";
import { renderMarkdown } from "./markdown.js";
import { SVG } from "./icons.js";

// Constantes — fonte única para valores que aparecem em múltiplos contextos.
const ACCENT_COLOR = "#6ea8fe";        // sincronizar com --accent em styles.css
const STATUS_LABELS = { idle: "idle", running: "running", done: "done", error: "error" };

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

threadEl.textContent = "thread: " + agent.threadId;

// Estado de renderização (correlação por id, conforme o protocolo).
const assistantBubbles = new Map(); // messageId -> { el, body }
const toolCards = new Map();        // toolCallId -> { card, argsEl, resultEl, buffer }

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
  wrapper.querySelector(".who").textContent = label;
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
    `<span class="etype ${cls}">${type}</span> ` +
    `<span class="payload">${escapeHtml(JSON.stringify(rest))}</span>`;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
  bumpBadge("events");
  // Console do navegador — para verificação do SSE/protocolo.
  console.log("%c[AG-UI] " + type, "color:" + ACCENT_COLOR, event);
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
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
  onStepStartedEvent: ({ event }) => {
    currentAction = event.stepName || "trabalhando";
  },
  onRunStartedEvent: () => {
    setStatus("running");
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
    runStartTime = null;
    if (runBubble) setAgentStatus(runBubble.wrapper, "", "Agent (" + total + ")", "");
    if (pendingAgentBlock) {
      // Run sem texto (ex.: só tool calls): descarta o spinner pendente.
      pendingAgentBlock.wrapper.remove();
      pendingAgentBlock = null;
    }
    finalizeRun("done");
    runBubble = null;
    assistantBubbles.clear();
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
    b.body.innerHTML = renderMarkdown(b.raw) + '<i class="blink"></i>';
    chatEl.scrollTop = chatEl.scrollHeight;
  },
  onTextMessageEndEvent: ({ event }) => {
    const b = assistantBubbles.get(event.messageId);
    if (b) {
      b.el.classList.remove("streaming");
      b.body.innerHTML = renderMarkdown(b.raw);
    }
  },

  // Tool calls
  onToolCallStartEvent: ({ event }) => {
    currentAction = event.toolCallName || "usando ferramenta";
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
  // Fonte autoritativa dos argumentos (oficial, agnóstica de provider): as
  // mensagens reconstruídas pelo cliente. Preenche os args de cada tool card.
  onMessagesChanged: ({ messages }) => {
    if (!Array.isArray(messages)) return;
    for (const m of messages) {
      const calls = m.toolCalls || m.tool_calls;
      if (!calls) continue;
      for (const call of calls) {
        const t = toolCards.get(call.id);
        if (!t || t.argsShown) continue;
        setToolArgs(t, call.function?.arguments ?? call.args);
      }
    }
  },

  // Estado compartilhado — renderiza genericamente todo o snapshot.
  onStateSnapshotEvent: ({ event }) => renderState(event.snapshot),
  // onStateChanged dá o estado reconstruído (após snapshot OU delta) — fonte única.
  onStateChanged: ({ state }) => renderState(state),

  // Human-in-the-loop: interrupt chega como CUSTOM com name "on_interrupt".
  onCustomEvent: ({ event }) => {
    if (event.name === "on_interrupt") {
      showApproval(event.value);
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
function showApproval(value) {
  // O valor do interrupt pode chegar como objeto ou como string JSON.
  let v = value;
  if (typeof v === "string") {
    try { v = JSON.parse(v); } catch { /* mantém string */ }
  }

  // Renderização GENÉRICA do interrupt (o protocolo passa `value` verbatim, app-defined):
  // destaca um campo textual (question/message/description/prompt) se houver e mostra o
  // valor completo como JSON. Sem conhecer nenhuma ação específica.
  approvalText.innerHTML = "";
  if (v && typeof v === "object") {
    const lead = v.question || v.message || v.description || v.prompt;
    if (lead) {
      const p = document.createElement("p");
      p.className = "approval-lead";
      p.textContent = String(lead);
      approvalText.appendChild(p);
    }
    const pre = document.createElement("pre");
    pre.className = "approval-json mono";
    pre.textContent = JSON.stringify(v, null, 2);
    approvalText.appendChild(pre);
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
  await agent.runAgent({
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
    await agent.runAgent({ runId: crypto.randomUUID() });
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
    if (size) {
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
