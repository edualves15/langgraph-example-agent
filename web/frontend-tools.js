// Tools de frontend GENÉRICAS de UI (ações client-side anunciadas ao agente em runtime).
//
// São agnósticas de domínio: renderizam um componente interativo INLINE no chat,
// aguardam a interação do usuário e devolvem o resultado como `ToolMessage` ao agente.
// O significado de negócio (cardápio, reservas, etc.) vem do BACKEND e do raciocínio do
// agente — aqui só existem primitivos de UI. Se `FRONTEND_TOOLS = []`, o cliente
// (app.js) volta a ser um renderizador AG-UI 100% genérico.
//
// Contrato (AG-UI): cada tool tem { name, description, parameters } anunciado ao agente
// + um `handler(args, { container })` que renderiza no `container` (nó inline no chat) e
// RETORNA a string (conteúdo do ToolMessage). Ver https://docs.ag-ui.com/concepts/tools

import { cardList, optionList, confirmDialog, buttonGroup, numberStepper } from "./ui-components.js";

// Ícones por chave de estado para as tags de "escolhas feitas" acima do input (web/app.js).
// ÚNICO ponto de domínio dessas tags: uma chave sem ícone cai no rótulo humanizado (genérico).
// `{}` → tags 100% genéricas.
export const STATE_TAG_ICONS = {
  order: "🍽️",
  date: "📅",
  time: "🕒",
  party_size: "👥",
  customer_name: "👤",
};

export const FRONTEND_TOOLS = [
  {
    name: "present_cards",
    description:
      "Display a selectable list of cards in the chat and return the user's selection. " +
      "PREFER THIS over asking in plain text whenever the user must choose among items that " +
      "have a title/description/price (e.g. menu dishes). Pass the items in the `cards` " +
      "argument, each as {id, title, description, price}. Optionally pass `currency` " +
      "(ISO 4217, e.g. \"BRL\", \"USD\") to format numeric prices. Returns the selected card ids. " +
      "State the heading/question in your reply text; this tool renders only the controls — do not repeat it.",
    parameters: {
      type: "object",
      properties: {
        cards: {
          type: "array",
          description: "The cards to show.",
          items: {
            type: "object",
            properties: {
              id: { type: "string" },
              title: { type: "string" },
              description: { type: "string" },
              price: { type: "number" },
            },
            required: ["id", "title"],
          },
        },
        currency: {
          type: "string",
          description: "Optional ISO 4217 currency code to format prices (e.g. BRL).",
        },
        multiple: {
          type: "boolean",
          description: "Allow selecting more than one card (default true).",
        },
      },
      required: ["cards"],
    },
    handler: async ({ cards, items, currency, multiple }, { container }) => {
      // Tolerante a desvios do modelo no nome do argumento (cards/items).
      const ids = await cardList(container, {
        cards: cards || items || [],
        currency,
        multiple: multiple !== false,
      });
      return JSON.stringify({ selected: ids });
    },
  },
  {
    name: "present_options",
    description:
      "Display a list of options in the chat (checkboxes when multiple, radios when " +
      "single) and return what the user selected. PREFER THIS over a free-text question " +
      "whenever the choice is among a known set of simple options (e.g. available time " +
      "slots, sizes). Returns the selected options. " +
      "State the heading/question in your reply text; this tool renders only the controls — do not repeat it.",
    parameters: {
      type: "object",
      properties: {
        options: {
          type: "array",
          items: { type: "string" },
          description: "The selectable options.",
        },
        multiple: {
          type: "boolean",
          description: "Allow selecting more than one option (default false).",
        },
      },
      required: ["options"],
    },
    handler: async ({ options, items, multiple }, { container }) => {
      const selected = await optionList(container, {
        options: options || items || [],
        multiple: multiple === true,
      });
      return JSON.stringify({ selected });
    },
  },
  {
    name: "present_buttons",
    description:
      "Display a row of one-tap quick-reply buttons in the chat and return the value of " +
      "the button the user clicks (no separate confirm step). PREFER THIS over asking in " +
      "plain text whenever the reply is a short single choice from a small set you can " +
      "enumerate — yes/no, a quantity (e.g. party size), picking one short option, OR " +
      "deciding between alternative next steps / courses of action (e.g. \"do X or Y?\", " +
      "proceed vs go back, this path vs that path). Whenever your question ends in \"... or " +
      "...?\" and the alternatives are short, render them as buttons instead of asking the " +
      "user to type. Each button is {label, value?, kind?}: `label` is shown, `value` is " +
      "returned when set (else the label is returned), and `kind` styles it as one of " +
      "neutral (default, subtle), primary (the single main action — use sparingly), danger " +
      "(destructive/decline) or success. Keep most buttons neutral and mark at most one as " +
      "primary. Returns the chosen value. " +
      "State the heading/question in your reply text; this tool renders only the controls — do not repeat it.",
    parameters: {
      type: "object",
      properties: {
        buttons: {
          type: "array",
          description: "The buttons to show (one tap returns its value).",
          items: {
            type: "object",
            properties: {
              label: { type: "string", description: "Text shown on the button." },
              value: {
                type: "string",
                description: "Value returned when clicked (defaults to the label).",
              },
              kind: {
                type: "string",
                enum: ["primary", "neutral", "danger", "success"],
                description: "Visual style (default neutral; use primary for at most one button).",
              },
            },
            required: ["label"],
          },
        },
      },
      required: ["buttons"],
    },
    handler: async ({ buttons, options }, { container }) => {
      const value = await buttonGroup(container, {
        buttons: buttons || options || [],
      });
      return JSON.stringify({ value });
    },
  },
  {
    name: "present_number",
    description:
      "Show a number stepper (− / + with an editable field) in the chat and return the " +
      "number the user picks. PREFER THIS over asking in plain text whenever the answer is " +
      "a quantity within a range — e.g. party size, how many items. Pass `min`, `max` and " +
      "`step` to bound it and `value` for the initial number. Returns the chosen number. " +
      "State the heading/question in your reply text; this tool renders only the controls — do not repeat it.",
    parameters: {
      type: "object",
      properties: {
        min: { type: "number", description: "Minimum allowed (default 1)." },
        max: { type: "number", description: "Maximum allowed (optional)." },
        step: { type: "number", description: "Increment between values (default 1)." },
        value: { type: "number", description: "Initial value (default = min)." },
      },
    },
    handler: async ({ min, max, step, value }, { container }) => {
      const chosen = await numberStepper(container, { min, max, step, value });
      return JSON.stringify({ value: chosen });
    },
  },
  {
    name: "confirm_dialog",
    description:
      "Show an inline Yes/No confirmation dialog (just the two buttons) and return the " +
      "user's decision. PREFER THIS over asking a yes/no question in plain text, to confirm " +
      "a choice or action before proceeding. Returns whether the user confirmed. " +
      "State what is being confirmed in your reply text; this tool renders only the buttons — do not repeat it.",
    parameters: {
      type: "object",
      properties: {},
    },
    handler: async (_args, { container }) => {
      const confirmed = await confirmDialog(container);
      return confirmed ? "O usuário confirmou." : "O usuário recusou.";
    },
  },
];
