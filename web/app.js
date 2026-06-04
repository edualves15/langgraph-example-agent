// Demonstração oficial do protocolo AG-UI sobre um agente LangGraph.
// Usa o cliente oficial @ag-ui/client (HttpAgent + AgentSubscriber).
// Cada evento recebido é logado no painel e no console do navegador, com os
// nomes de campos canônicos (type em SCREAMING_SNAKE_CASE, campos em camelCase).
import { HttpAgent } from "https://esm.sh/@ag-ui/client@0.0.55";

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
const proverbsEl = $("proverbs");
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
  statusEl.textContent = s;
  statusEl.className = "status " + s;
}

function addUserBubble(text) {
  const el = document.createElement("div");
  el.className = "bubble user";
  el.innerHTML = `<div class="who">você</div>`;
  el.append(document.createTextNode(text));
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function getAssistantBubble(messageId) {
  let entry = assistantBubbles.get(messageId);
  if (!entry) {
    const el = document.createElement("div");
    el.className = "bubble assistant streaming";
    el.innerHTML = `<div class="who">agente</div>`;
    const body = document.createElement("span");
    el.appendChild(body);
    chatEl.appendChild(el);
    entry = { el, body };
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
  console.log("%c[AG-UI] " + type, "color:#6ea8fe", event);
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function renderProverbs(proverbs) {
  proverbsEl.innerHTML = "";
  if (!proverbs || proverbs.length === 0) {
    proverbsEl.innerHTML = `<li class="empty">— vazio —</li>`;
    return;
  }
  for (const p of proverbs) {
    const li = document.createElement("li");
    li.textContent = p;
    proverbsEl.appendChild(li);
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

// Tag de origem/categoria da ferramenta (apenas apresentação no front — não
// altera o protocolo). Mapeia o nome oficial da tool para um rótulo legível.
const TOOL_TAGS = {
  get_today_info: "calendar", get_date_details: "calendar", calculate_date_difference: "calendar",
  shift_date: "calendar", count_business_days: "calendar", add_business_days: "calendar",
  find_next_weekday: "calendar", list_dates_in_range: "calendar",
  calculate_math_expression: "math",
  add_proverb: "state", set_proverbs: "state",
  send_email: "hitl",
  tavily_search: "web", tavily_extract: "web",
};
const TAG_LABELS = {
  calendar: "📅 calendário", math: "🔢 cálculo", state: "🧩 estado",
  hitl: "🙋 aprovação", web: "🔎 web", backend: "⚙️ backend",
};
function toolTag(name) {
  const key = TOOL_TAGS[name] || "backend";
  return { key, label: TAG_LABELS[key] };
}

// ---------------------------------------------------------------------------
// Subscriber oficial — um handler por categoria de evento AG-UI.
// ---------------------------------------------------------------------------
const subscriber = {
  // Catch-all: registra TODOS os eventos (log + console).
  onEvent: ({ event }) => logEvent(event),

  // Lifecycle
  onRunStartedEvent: () => setStatus("running"),
  onRunFinishedEvent: () => finalizeRun("done"),
  onRunErrorEvent: ({ event }) => {
    finalizeRun("error");
    const b = getAssistantBubble("error-" + Date.now());
    b.body.textContent = "⚠️ " + (event.message || "Erro na execução.");
  },

  // Mensagens de texto (streaming)
  onTextMessageStartEvent: ({ event }) => getAssistantBubble(event.messageId),
  onTextMessageContentEvent: ({ event }) => {
    const b = getAssistantBubble(event.messageId);
    b.body.append(event.delta);
    chatEl.scrollTop = chatEl.scrollHeight;
  },
  onTextMessageEndEvent: ({ event }) => {
    const b = assistantBubbles.get(event.messageId);
    if (b) b.el.classList.remove("streaming");
  },

  // Tool calls
  onToolCallStartEvent: ({ event }) => {
    const tag = toolTag(event.toolCallName);
    const card = document.createElement("div");
    card.className = "tool-card";
    card.innerHTML =
      `<div class="t-head">` +
        `<span class="dot"></span>` +
        `<span class="ttag ttag-${tag.key}">${tag.label}</span>` +
        `<span class="tname">${escapeHtml(event.toolCallName)}</span>` +
        `<span class="tid">${escapeHtml(event.toolCallId.slice(0, 8))}</span>` +
      `</div>` +
      `<div class="t-body">` +
        `<div class="field args-field" hidden><span class="lbl">argumentos</span><pre class="args"></pre></div>` +
        `<div class="field result-field" hidden><span class="lbl">resultado</span><pre class="result"></pre></div>` +
      `</div>`;
    if (toolsEl.querySelector(".empty")) toolsEl.innerHTML = "";
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
    if (!t) return;
    t.buffer += event.delta;
    setToolArgs(t, t.buffer);
  },
  onToolCallEndEvent: ({ event }) => {
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

  // Estado compartilhado
  onStateSnapshotEvent: ({ event }) => renderProverbs(event.snapshot?.proverbs),
  // onStateChanged dá o estado reconstruído (após snapshot OU delta) — fonte única.
  onStateChanged: ({ state }) => renderProverbs(state?.proverbs),

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
  sendBtn.disabled = false;
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

  if (v && typeof v === "object" && v.action === "send_email") {
    // Demo de envio de e-mail: mostra o rascunho completo para aprovação.
    approvalText.innerHTML =
      `<div class="email-draft">` +
      `<div><span class="k">Para:</span> ${escapeHtml(v.to || "")}</div>` +
      `<div><span class="k">Assunto:</span> ${escapeHtml(v.subject || "")}</div>` +
      `<pre class="email-body">${escapeHtml(v.body || "")}</pre>` +
      `</div>`;
  } else {
    const text = (v && typeof v === "object" && (v.question || v.action)) || v || "Confirmar ação?";
    approvalText.textContent = typeof text === "string" ? text : JSON.stringify(text);
  }
  approvalEl.classList.remove("hidden");
}

async function resolveApproval(approved) {
  approvalEl.classList.add("hidden");
  setStatus("running");
  sendBtn.disabled = true;
  // Retoma a MESMA thread enviando o comando de resume ao LangGraph.
  await agent.runAgent({
    runId: crypto.randomUUID(),
    forwardedProps: { command: { resume: { approved } } },
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

$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = inputEl.value;
  inputEl.value = "";
  send(text);
});

$("suggestions").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-prompt]");
  if (btn) send(btn.dataset.prompt);
});

$("clear-log").addEventListener("click", (e) => {
  e.stopPropagation();
  logEl.innerHTML = "";
});

// ---------------------------------------------------------------------------
// Abas do painel de debug + contadores totais (tool calls / eventos)
// ---------------------------------------------------------------------------
const tabsEl = document.querySelector(".tabs");
const counters = { tools: 0, events: 0 };

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
  badge.hidden = false;
}

tabsEl.addEventListener("click", (e) => {
  const btn = e.target.closest(".tab");
  if (btn) setActiveTab(btn.dataset.tab);
});
