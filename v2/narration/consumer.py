"""
Consumer de terminal para NarrationEvent.

Renderiza eventos canonicos com formatacao visual para desenvolvimento local.
O encoding e tratado pelo _safe_print / _asciify de v2/main.py.
"""

from __future__ import annotations

import sys
import unicodedata
from typing import Callable

from v2.narration.events import NarrationEvent

# ---------------------------------------------------------------------------
# Encoding (replicado aqui para o consumer ser autossuficiente)
# ---------------------------------------------------------------------------

_ICON_FALLBACK: dict[str, str] = {
    "📅": "[cal]",
    "🔢": "[mat]",
}


def _asciify(text: str) -> str:
    """Remove acentos preservando legibilidade."""
    if not text:
        return text
    try:
        text.encode(sys.stdout.encoding)
        return text
    except (UnicodeEncodeError, LookupError):
        pass
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _safe_print(*args, **kwargs) -> None:
    """print() resiliente a qualquer encoding de terminal."""
    cleaned = [_asciify(a) if isinstance(a, str) else a for a in args]
    try:
        print(*cleaned, **kwargs)
    except UnicodeEncodeError:
        ascii_args = [
            a.encode("ascii", errors="replace").decode("ascii") if isinstance(a, str) else a
            for a in cleaned
        ]
        print(*ascii_args, **kwargs)


def _safe_icon(icon: str) -> str:
    """Retorna o icone ou fallback se o terminal nao suportar Unicode."""
    if not icon:
        return ""
    try:
        icon.encode(sys.stdout.encoding)
        return icon
    except UnicodeEncodeError:
        return _ICON_FALLBACK.get(icon, "")


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def render_event(event: NarrationEvent) -> None:
    """Renderiza um NarrationEvent no terminal com formatacao visual.

    Mapeamento:
        run_started      → "========== Iniciando =========="
        run_finished     → "========== Concluido =========="
        step_started     → "  --- {text} ---"
        step_finished    → (silencioso)
        tool_call/start  → "  >  {icon} {text}"
        tool_result      → "  ✓  {icon} {text}"
        block_start       → (silencioso — ja anunciado)
        block_delta       → (silencioso — progresso interno)
        block_stop        → (silencioso — tool_result cobre)
        text_delta        → (tratado separadamente no streaming)
        error            → "  ✗  {icon} {text}: {error}"
    """
    etype = event.type
    stage = event.stage
    text = event.text
    icon = _safe_icon(event.icon)
    prefix = f"{icon} " if icon else ""

    if etype == "run_started":
        _safe_print("=" * 60)

    elif etype == "run_finished":
        _safe_print("=" * 60 + "\n")

    elif etype == "step_started":
        pass  # terminal nao renderiza step labels

    elif etype == "step_finished":
        pass

    elif etype == "reasoning_started":
        p = prefix if prefix else "💭 "
        _safe_print(f"  >  {p}{text}")

    elif etype == "reasoning_stop":
        pass

    elif etype == "tool_call" and stage == "start":
        # Anuncio pre-execucao (agent_node)
        _safe_print(f"  >  {prefix}{text}")

    elif etype == "tool_result":
        _safe_print(f"  ✓  {prefix}{text}")

    elif etype == "error":
        err = event.error
        _safe_print(f"  ✗  {prefix}{text}: {err}")

    elif etype == "tool_call" and stage == "stop":
        pass  # tool_result ja cobre o resultado

    # block_start / block_delta / block_stop sao silenciosos no terminal
    # — existem para o front-end rastrear progresso interno
