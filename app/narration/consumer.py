"""
Consumer de terminal para NarrationEvent.

Renderiza eventos canonicos com formatacao visual para desenvolvimento local.
"""

from __future__ import annotations

import sys
import unicodedata

from app.narration.events import NarrationEvent

# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

_ICON_FALLBACK: dict[str, str] = {
    "📅": "[cal]",
    "🔢": "[mat]",
    "🔍": "[srch]",
    "📄": "[doc]",
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
    """Renderiza um NarrationEvent no terminal com formatacao visual."""
    etype = event.type
    stage = event.stage
    text = event.text
    icon = _safe_icon(event.icon)
    prefix = f"{icon} " if icon else ""

    if etype == "run_started":
        _safe_print("=" * 60)

    elif etype == "run_finished":
        _safe_print("=" * 60 + "\n")

    elif etype in ("step_started", "step_finished"):
        pass

    elif etype == "reasoning_started":
        p = prefix if prefix else "💭 "
        _safe_print(f"  >  {p}{text}")

    elif etype == "reasoning_end":
        pass

    elif etype == "tool_call" and stage == "start":
        _safe_print(f"  >  {prefix}{text}")

    elif etype == "tool_result":
        _safe_print(f"  ✓  {prefix}{text}")

    elif etype == "error":
        err = event.error
        _safe_print(f"  ✗  {prefix}{text}: {err}")

    elif etype == "tool_call" and stage == "stop":
        pass
