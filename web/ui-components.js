// Toolkit de widgets de UI GENÉRICOS (sem conhecimento de negócio).
//
// Cada widget renderiza dentro de um `container` (um nó DOM fornecido pelo chamador)
// e devolve uma Promise que resolve quando o usuário interage. São reutilizáveis em
// qualquer domínio — quem dá significado de negócio são as tools de frontend
// (web/frontend-tools.js) que os compõem.

import { escapeHtml } from "./escape.js";

// Formatação de preço AGNÓSTICA de moeda: string já formatada pelo domínio passa
// direto; número só vira moeda se um `currency` (ISO 4217) for fornecido em runtime —
// caso contrário é renderizado cru. Nenhuma moeda fica hardcoded no widget.
function formatPrice(v, currency) {
  if (v == null || v === "") return "";
  if (typeof v === "string") return v;
  if (typeof v !== "number") return "";
  if (currency) {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(v);
    } catch {
      /* código de moeda inválido → cai para número cru */
    }
  }
  return String(v);
}

// Marca o widget como concluído: desabilita interação e congela a escolha.
function finish(root, resolveBtn) {
  root.classList.add("uic-done");
  root.querySelectorAll("input, button").forEach((el) => (el.disabled = true));
  if (resolveBtn) resolveBtn.textContent = "✓ Enviado";
}

/**
 * Lista de opções com checkboxes (multiple) ou radios (single) + botão confirmar.
 * Resolve com um array das opções (strings) selecionadas.
 */
export function optionList(container, { options, multiple = true }) {
  return new Promise((resolve) => {
    const root = document.createElement("div");
    root.className = "uic uic-options";
    const type = multiple ? "checkbox" : "radio";
    const name = "opt-" + Math.random().toString(36).slice(2);
    root.innerHTML =
      `<div class="uic-list">` +
      (options || [])
        .map(
          (opt) =>
            `<label class="uic-opt"><input type="${type}" name="${name}" value="${escapeHtml(opt)}"> <span>${escapeHtml(opt)}</span></label>`,
        )
        .join("") +
      `</div>` +
      `<button type="button" class="uic-btn uic-btn--primary uic-confirm">Confirmar</button>`;

    const btn = root.querySelector(".uic-confirm");
    // "Confirmar" só habilita com ≥1 opção marcada — impede envio de resposta vazia.
    btn.disabled = true;
    root.querySelector(".uic-list").addEventListener("change", () => {
      btn.disabled = root.querySelectorAll("input:checked").length === 0;
    });
    btn.addEventListener("click", () => {
      const selected = Array.from(
        root.querySelectorAll("input:checked"),
        (el) => el.value,
      );
      finish(root, btn);
      resolve(selected);
    });

    container.appendChild(root);
  });
}

/**
 * Lista de cards selecionáveis ({ id, title, description, price }) + confirmar.
 * Resolve com um array dos `id`s selecionados.
 */
export function cardList(container, { cards, multiple = true, currency }) {
  return new Promise((resolve) => {
    const root = document.createElement("div");
    root.className = "uic uic-cards";
    root.innerHTML =
      `<div class="uic-card-grid">` +
      (cards || [])
        .map(
          (c) =>
            `<button type="button" class="uic-card" data-id="${escapeHtml(c.id)}">` +
            `<span class="uic-card-title">${escapeHtml(c.title ?? c.name ?? c.id)}</span>` +
            (c.description ? `<span class="uic-card-desc">${escapeHtml(c.description)}</span>` : "") +
            (c.price != null ? `<span class="uic-card-price">${escapeHtml(formatPrice(c.price, currency))}</span>` : "") +
            `</button>`,
        )
        .join("") +
      `</div>` +
      `<button type="button" class="uic-btn uic-btn--primary uic-confirm">Confirmar</button>`;

    const btn = root.querySelector(".uic-confirm");
    // "Confirmar" só habilita com ≥1 card selecionado — impede envio de resposta vazia.
    btn.disabled = true;

    const selected = new Set();
    root.querySelectorAll(".uic-card").forEach((card) => {
      card.addEventListener("click", () => {
        const id = card.dataset.id;
        if (!multiple) {
          selected.clear();
          root.querySelectorAll(".uic-card").forEach((c) => c.classList.remove("sel"));
        }
        if (selected.has(id)) {
          selected.delete(id);
          card.classList.remove("sel");
        } else {
          selected.add(id);
          card.classList.add("sel");
        }
        btn.disabled = selected.size === 0;
      });
    });

    btn.addEventListener("click", () => {
      finish(root, btn);
      resolve(Array.from(selected));
    });

    container.appendChild(root);
  });
}

// Variantes visuais permitidas para os botões de resposta rápida. Saneadas contra
// esta whitelist (valor desconhecido/ausente → "neutral"): evita injeção de classe e
// mantém o widget genérico/flat.
const BUTTON_KINDS = ["primary", "neutral", "danger", "success"];

/**
 * Linha de botões de resposta rápida. Cada botão = { label, value, kind }.
 * Clicar resolve IMEDIATAMENTE (sem etapa de confirmar) com `value ?? label`.
 * `kind` ∈ {primary, neutral, danger, success} → classe .uic-btn--<kind> (default neutral;
 * use primary só no botão de ação principal).
 */
export function buttonGroup(container, { buttons }) {
  return new Promise((resolve) => {
    const root = document.createElement("div");
    root.className = "uic uic-buttons";
    root.innerHTML =
      `<div class="uic-btn-row">` +
      (buttons || [])
        .map((b) => {
          const label = b.label ?? b.title ?? b.value ?? "";
          const kind = BUTTON_KINDS.includes(b.kind) ? b.kind : "neutral";
          const value = b.value ?? label;
          return (
            `<button type="button" class="uic-btn uic-btn--${kind}" ` +
            `data-value="${escapeHtml(value)}">${escapeHtml(label)}</button>`
          );
        })
        .join("") +
      `</div>`;

    root.querySelectorAll(".uic-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        finish(root, null);
        btn.classList.add("chosen");
        resolve(btn.dataset.value);
      });
    });

    container.appendChild(root);
  });
}

/**
 * Seletor de número (stepper −/+ com botão Confirmar). Resolve com o número escolhido
 * (string, p/ o ToolMessage). Opções: { title, min=1, max, step=1, value }.
 * − / + e o input respeitam [min, max] e alinham ao `step`; input editável pelo teclado.
 */
export function numberStepper(container, { min = 1, max, step = 1, value } = {}) {
  return new Promise((resolve) => {
    const lo = Number.isFinite(min) ? min : 1;
    const hi = Number.isFinite(max) ? max : null;
    const st = Number.isFinite(step) && step > 0 ? step : 1;
    const clamp = (n) => {
      if (!Number.isFinite(n)) return lo;
      n = Math.round((n - lo) / st) * st + lo; // alinha à grade do step
      if (n < lo) n = lo;
      if (hi != null && n > hi) n = hi;
      return n;
    };
    let val = clamp(Number.isFinite(value) ? value : lo);

    const root = document.createElement("div");
    root.className = "uic uic-stepper-wrap";
    root.innerHTML =
      `<div class="uic-stepper">` +
        `<button type="button" class="uic-btn uic-btn--icon uic-btn--neutral uic-step" data-d="-1" aria-label="Diminuir">−</button>` +
        `<input class="uic-step-val" type="number" inputmode="numeric" value="${val}">` +
        `<button type="button" class="uic-btn uic-btn--icon uic-btn--neutral uic-step" data-d="1" aria-label="Aumentar">+</button>` +
      `</div>` +
      `<button type="button" class="uic-btn uic-btn--primary uic-confirm">Confirmar</button>`;

    const input = root.querySelector(".uic-step-val");
    const sync = () => { input.value = String(val); };
    root.querySelectorAll(".uic-step").forEach((b) => {
      b.addEventListener("click", () => {
        val = clamp(Number(input.value) + st * Number(b.dataset.d));
        sync();
      });
    });
    input.addEventListener("blur", () => { val = clamp(Number(input.value)); sync(); });

    const confirm = root.querySelector(".uic-confirm");
    confirm.addEventListener("click", () => {
      val = clamp(Number(input.value));
      finish(root, confirm);
      resolve(String(val));
    });

    container.appendChild(root);
  });
}

/**
 * Dialog inline de confirmação (Sim/Não). Resolve com booleano.
 * Só os botões — a pergunta vem da resposta do agente.
 */
export function confirmDialog(container) {
  return new Promise((resolve) => {
    const root = document.createElement("div");
    root.className = "uic uic-dialog";
    root.innerHTML =
      `<div class="uic-actions">` +
      `<button type="button" class="uic-btn uic-btn--primary uic-yes">Sim</button>` +
      `<button type="button" class="uic-btn uic-btn--neutral uic-no">Não</button>` +
      `</div>`;

    const done = (value) => {
      finish(root, null);
      root.querySelector(value ? ".uic-yes" : ".uic-no").classList.add("chosen");
      resolve(value);
    };
    root.querySelector(".uic-yes").addEventListener("click", () => done(true));
    root.querySelector(".uic-no").addEventListener("click", () => done(false));

    container.appendChild(root);
  });
}
