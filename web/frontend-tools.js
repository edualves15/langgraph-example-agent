// Ações client-side (frontend tools) específicas DESTE app.
//
// Este é o ÚNICO lugar com conhecimento de negócio do front. O cliente genérico
// (`app.js`) não conhece nomes de tools — apenas itera `FRONTEND_TOOLS`, anuncia os
// schemas ao agente em runtime (campo `tools` do RunAgentInput) e executa os
// `handler`s no navegador quando o agente as chama. Se este arquivo exportar `[]`,
// `app.js` volta a ser um cliente AG-UI 100% genérico.
//
// Contrato de cada tool (AG-UI): { name, description, parameters } anunciado ao agente
// + um `handler(args)` que roda no navegador e RETORNA o conteúdo (string) que vira o
// `ToolMessage` devolvido ao agente. Ver https://docs.ag-ui.com/concepts/tools

// Estado DONO DA UI (não do agente): vive e é renderizado só no front.
let proverbs = [];
let mountEl = null;

/** Recebe de `app.js` um nó DOM neutro onde este módulo renderiza o que quiser. */
export function mountFrontendTools(el) {
  mountEl = el;
  render();
}

function render() {
  if (!mountEl) return;
  if (proverbs.length === 0) {
    mountEl.innerHTML = `<div class="tab-empty">Nenhum provérbio (estado dono da UI)</div>`;
    return;
  }
  const items = proverbs
    .map((p) => `<li>${escapeHtml(p)}</li>`)
    .join("");
  mountEl.innerHTML =
    `<div class="ft-title mono">proverbs · array[${proverbs.length}]</div>` +
    `<ol class="ft-proverbs">${items}</ol>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

export const FRONTEND_TOOLS = [
  {
    name: "setProverbs",
    description:
      "Replace the entire list of proverbs shown in the UI with the provided list " +
      "(pass an empty list to clear). Use when the user asks to set, reset, replace, " +
      "or clear the proverbs.",
    parameters: {
      type: "object",
      properties: {
        proverbs: {
          type: "array",
          items: { type: "string" },
          description: "The new list of proverbs (may be empty).",
        },
      },
      required: ["proverbs"],
    },
    handler: ({ proverbs: next }) => {
      proverbs = Array.isArray(next) ? next.map(String) : [];
      render();
      return `Lista de provérbios definida com ${proverbs.length} item(ns).`;
    },
  },
  {
    name: "addProverb",
    description:
      "Append a single proverb to the list shown in the UI. Use when the user asks to " +
      "create, add, or invent a proverb.",
    parameters: {
      type: "object",
      properties: {
        proverb: { type: "string", description: "A short, original saying to append." },
      },
      required: ["proverb"],
    },
    handler: ({ proverb }) => {
      proverbs.push(String(proverb));
      render();
      return `Provérbio adicionado. Agora há ${proverbs.length} provérbio(s).`;
    },
  },
];
