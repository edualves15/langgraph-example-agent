from datetime import date

from langchain_core.tools import tool

# Exemplo local. Em produção, conecte aqui seu calendário privado/banco interno.
_FAKE_EVENTS = {
    "2026-05-29": ["Revisão semanal às 10:00", "Alinhamento técnico às 16:00"],
}


@tool
def get_events(day: str) -> str:
    """Consulta eventos locais de calendário para uma data YYYY-MM-DD."""
    events = _FAKE_EVENTS.get(day, [])
    if not events:
        return f"Nenhum evento encontrado para {day}."
    return f"Eventos em {day}: " + "; ".join(events)


@tool
def today() -> str:
    """Retorna a data atual local no formato YYYY-MM-DD."""
    return date.today().isoformat()
