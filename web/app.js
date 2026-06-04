// Demonstração oficial do protocolo AG-UI sobre um agente LangGraph.
// Usa o cliente oficial @ag-ui/client (HttpAgent + AgentSubscriber).
// Cada evento recebido é logado no painel e no console do navegador, com os
// nomes de campos canônicos (type em SCREAMING_SNAKE_CASE, campos em camelCase).
import { HttpAgent } from "https://esm.sh/@ag-ui/client@0.0.55";

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
    const card = document.createElement("div");
    card.className = "tool-card";
    card.innerHTML =
      `<div class="t-head"><span>${event.toolCallName}</span><span>${event.toolCallId.slice(0, 8)}</span></div>` +
      `<div class="t-body"><div class="lbl">args</div><pre class="args"></pre>` +
      `<div class="lbl result-lbl" style="display:none">result</div><pre class="result"></pre></div>`;
    if (toolsEl.querySelector(".empty")) toolsEl.innerHTML = "";
    toolsEl.appendChild(card);
    toolCards.set(event.toolCallId, {
      card,
      argsEl: card.querySelector(".args"),
      resultEl: card.querySelector(".result"),
      resultLbl: card.querySelector(".result-lbl"),
      buffer: "",
    });
  },
  onToolCallArgsEvent: ({ event }) => {
    const t = toolCards.get(event.toolCallId);
    if (!t) return;
    t.buffer += event.delta;
    t.argsEl.textContent = t.buffer;
  },
  onToolCallEndEvent: ({ event }) => {
    const t = toolCards.get(event.toolCallId);
    if (t) t.card.classList.add("done");
  },
  onToolCallResultEvent: ({ event }) => {
    const t = toolCards.get(event.toolCallId);
    if (!t) return;
    t.resultLbl.style.display = "block";
    t.resultEl.textContent = event.content;
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
  const text = (v && typeof v === "object" && (v.question || v.action)) || v || "Confirmar ação?";
  approvalText.textContent = typeof text === "string" ? text : JSON.stringify(text);
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

$("clear-log").addEventListener("click", () => (logEl.innerHTML = ""));
