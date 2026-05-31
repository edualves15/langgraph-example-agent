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


get_events.metadata = {
    "step_label": "Consultando calendário para {day}",
    "step_done_label": "Calendário consultado",
    "step_icon": "calendar",
    "step_category": "lookup",
}


@tool
def today() -> str:
    """Retorna a data atual local no formato YYYY-MM-DD."""
    return date.today().isoformat()


today.metadata = {
    "step_label": "Verificando a data atual",
    "step_done_label": "Data obtida",
    "step_icon": "clock",
    "step_category": "system",
}


@tool
def days_between(start_date: str, end_date: str) -> str:
    """Calcula a diferença em dias entre duas datas no formato YYYY-MM-DD.
    Use end_date='today' para calcular até hoje.
    Exemplo: days_between('1536-04-01', 'today')
    """
    try:
        start = date.fromisoformat(start_date)
        end = date.today() if end_date.strip().lower() == "today" else date.fromisoformat(end_date)
        delta = (end - start).days
        return str(delta)
    except ValueError as exc:
        return f"Data inválida: {exc}. Use o formato YYYY-MM-DD."


days_between.metadata = {
    "step_label": "Calculando dias entre {start_date} e {end_date}",
    "step_done_label": "Diferença calculada",
    "step_icon": "clock",
    "step_category": "compute",
}
