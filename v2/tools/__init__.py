"""
Registro de tools e metadados de narracao.

Fornece NarrationMeta (schema tipado para metadados visuais das tools),
helpers de formatacao, e a lista ALL_TOOLS usada pelo grafo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# NarrationMeta
# ---------------------------------------------------------------------------

# Traducao de args para PT (reusada na formatacao de labels)
_WEEKDAY_PT: dict[str, str] = {
    "monday": "segunda-feira",
    "tuesday": "terça-feira",
    "wednesday": "quarta-feira",
    "thursday": "quinta-feira",
    "friday": "sexta-feira",
    "saturday": "sábado",
    "sunday": "domingo",
}
_DIRECTION_PT: dict[str, str] = {"next": "próxima ocorrência", "previous": "ocorrência anterior"}
_UNIT_PT: dict[str, str] = {"days": "dias", "weeks": "semanas", "months": "meses", "years": "anos"}


def _humanize(value: Any) -> Any:
    """Converte um arg de tool call para forma legivel em PT."""
    if not isinstance(value, str):
        return value
    v = value.strip().lower()
    if v in ("today", "hoje"):
        return "hoje"
    try:
        return date.fromisoformat(value.strip()).strftime("%d/%m/%Y")
    except ValueError:
        pass
    return _WEEKDAY_PT.get(v) or _DIRECTION_PT.get(v) or _UNIT_PT.get(v) or value


@dataclass(slots=True)
class NarrationMeta:
    """Metadados visuais de uma tool para o sistema de narracao.

    Attributes:
        icon: Emoji ou string de icone para UI.
        announce_template: Template para o anuncio pre-execucao.
            Usa {chaves} correspondentes aos argumentos da tool call.
            Ex: "Avançando {business_days} dias úteis desde {start_date}"
        done_label: Texto exibido quando a tool termina com sucesso.
        error_label: Texto exibido quando a tool falha.
        level: Nivel de progressive disclosure (1=resumo, 2=detalhe, 3=tecnico).
    """

    icon: str = ""
    announce_template: str = ""
    done_label: str = ""
    error_label: str = ""
    level: int = 2


def get_tool_narration(tool) -> NarrationMeta:
    """Extrai NarrationMeta de uma tool, com fallback para metadata antigo."""
    # Prefere .narration (novo)
    if hasattr(tool, "narration") and isinstance(tool.narration, NarrationMeta):
        return tool.narration

    # Fallback para .metadata (antigo) — converte on-the-fly
    meta = getattr(tool, "metadata", {}) or {}
    if meta:
        return NarrationMeta(
            icon=meta.get("step_icon", ""),
            announce_template=meta.get("step_label_template", meta.get("step_label", "")),
            done_label=meta.get("step_done_label", ""),
            error_label=meta.get("step_error_label", ""),
            level=2,
        )

    # Fallback final
    return NarrationMeta(
        announce_template=getattr(tool, "name", "unknown"),
        done_label="",
        error_label="",
    )


def format_narration_label(meta: NarrationMeta, tool_call: dict) -> str:
    """Resolve o label de progresso a partir do NarrationMeta e args da tool call.

    Preenche defaults da assinatura da tool para argumentos omitidos pelo LLM,
    garantindo que o template sempre resolva completamente.
    """
    import inspect
    import re

    template = meta.announce_template or tool_call.get("name", "unknown")
    args = {k: _humanize(v) for k, v in tool_call.get("args", {}).items()}

    # Pre-fill defaults from tool function signature (args omitidos pelo LLM)
    tool = TOOLS_BY_NAME.get(tool_call.get("name"))
    if tool is not None:
        try:
            sig = inspect.signature(tool.func)
            for name, param in sig.parameters.items():
                if name not in args and param.default is not inspect.Parameter.empty:
                    args[name] = _humanize(param.default)
        except Exception:
            pass

    try:
        return template.format(**args)
    except (KeyError, ValueError):
        # Fallback: substitui apenas as chaves presentes, remove ausentes
        return re.sub(r"\{(\w+)\}", lambda m: str(args.get(m.group(1), "")), template).strip()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

from v2.tools.calendar_tools import (
    add_business_days,
    calculate_date_difference,
    count_business_days,
    find_next_weekday,
    get_date_details,
    get_today_info,
    list_dates_in_range,
    shift_date,
)
from v2.tools.math_tools import calculate_math_expression

ALL_TOOLS = [
    calculate_math_expression,
    get_today_info,
    get_date_details,
    calculate_date_difference,
    shift_date,
    count_business_days,
    add_business_days,
    find_next_weekday,
    list_dates_in_range,
]

TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}
