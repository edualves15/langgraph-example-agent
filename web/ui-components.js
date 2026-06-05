// Toolkit de widgets de UI GENÉRICOS (sem conhecimento de negócio).
//
// Cada widget renderiza dentro de um `container` (um nó DOM fornecido pelo chamador)
// e devolve uma Promise que resolve quando o usuário interage. São reutilizáveis em
// qualquer domínio — quem dá significado de negócio são as tools de frontend
// (web/frontend-tools.js) que os compõem.

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]
  ));
}

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
export function optionList(container, { title, options, multiple = true }) {
  return new Promise((resolve) => {
    const root = document.createElement("div");
    root.className = "uic uic-options";
    const type = multiple ? "checkbox" : "radio";
    const name = "opt-" + Math.random().toString(36).slice(2);
    root.innerHTML =
      (title ? `<div class="uic-title">${escapeHtml(title)}</div>` : "") +
      `<div class="uic-list">` +
      (options || [])
        .map(
          (opt) =>
            `<label class="uic-opt"><input type="${type}" name="${name}" value="${escapeHtml(opt)}"> <span>${escapeHtml(opt)}</span></label>`,
        )
        .join("") +
      `</div>` +
      `<button type="button" class="uic-confirm">Confirmar</button>`;

    const btn = root.querySelector(".uic-confirm");
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
export function cardList(container, { title, cards, multiple = true, currency }) {
  return new Promise((resolve) => {
    const root = document.createElement("div");
    root.className = "uic uic-cards";
    root.innerHTML =
      (title ? `<div class="uic-title">${escapeHtml(title)}</div>` : "") +
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
      `<button type="button" class="uic-confirm">Confirmar</button>`;

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
      });
    });

    const btn = root.querySelector(".uic-confirm");
    btn.addEventListener("click", () => {
      finish(root, btn);
      resolve(Array.from(selected));
    });

    container.appendChild(root);
  });
}

/**
 * Dialog inline de confirmação (Sim/Não). Resolve com booleano.
 */
export function confirmDialog(container, { title, message }) {
  return new Promise((resolve) => {
    const root = document.createElement("div");
    root.className = "uic uic-dialog";
    root.innerHTML =
      (title ? `<div class="uic-title">${escapeHtml(title)}</div>` : "") +
      (message ? `<div class="uic-msg">${escapeHtml(message)}</div>` : "") +
      `<div class="uic-actions">` +
      `<button type="button" class="uic-yes">Sim</button>` +
      `<button type="button" class="uic-no">Não</button>` +
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
