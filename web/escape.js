// Escape de HTML compartilhado (anti-XSS) — fonte única para todo o front.
//
// Escapa os caracteres que quebrariam markup OU atributos com aspas duplas
// (`&`, `<`, `>`, `"`). `String(s)` garante robustez com entradas não-string.
// Usado por app.js, ui-components.js e markdown.js — não duplicar a lógica.
const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };

export function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => HTML_ESCAPES[c]);
}
