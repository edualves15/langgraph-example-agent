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

import { cardList, optionList, confirmDialog } from "./ui-components.js";

export const FRONTEND_TOOLS = [
  {
    name: "present_cards",
    description:
      "Display a selectable list of cards in the chat and return the user's selection. " +
      "Use to present options that have a title/description/price (e.g. menu dishes) and " +
      "let the user choose. Pass the items in the `cards` argument, each as " +
      "{id, title, description, price}. Returns the selected card ids.",
    parameters: {
      type: "object",
      properties: {
        title: { type: "string", description: "Heading shown above the cards." },
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
        multiple: {
          type: "boolean",
          description: "Allow selecting more than one card (default true).",
        },
      },
      required: ["title", "cards"],
    },
    handler: async ({ title, cards, items, multiple }, { container }) => {
      // Tolerante a desvios do modelo no nome do argumento (cards/items).
      const ids = await cardList(container, {
        title: title || "",
        cards: cards || items || [],
        multiple: multiple !== false,
      });
      return JSON.stringify({ selected: ids });
    },
  },
  {
    name: "present_options",
    description:
      "Display a list of options in the chat (checkboxes when multiple, radios when " +
      "single) and return what the user selected. Use for simple textual choices " +
      "(e.g. available time slots). Returns the selected options.",
    parameters: {
      type: "object",
      properties: {
        title: { type: "string", description: "Heading shown above the options." },
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
      required: ["title", "options"],
    },
    handler: async ({ title, options, items, multiple }, { container }) => {
      const selected = await optionList(container, {
        title: title || "",
        options: options || items || [],
        multiple: multiple === true,
      });
      return JSON.stringify({ selected });
    },
  },
  {
    name: "confirm_dialog",
    description:
      "Show an inline Yes/No confirmation dialog in the chat and return the user's " +
      "decision. Use to confirm a choice or action before proceeding. Returns whether " +
      "the user confirmed.",
    parameters: {
      type: "object",
      properties: {
        title: { type: "string", description: "Short dialog title." },
        message: { type: "string", description: "What the user is confirming." },
      },
      required: ["message"],
    },
    handler: async ({ title, message }, { container }) => {
      const confirmed = await confirmDialog(container, { title, message });
      return confirmed ? "O usuário confirmou." : "O usuário recusou.";
    },
  },
];
