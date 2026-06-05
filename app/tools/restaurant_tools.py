"""Ferramentas de backend do domínio Restaurante.

São tools de **backend** (efeito/dado server-side): o cardápio e os horários são a
fonte de verdade no servidor; `create_reservation` é o efeito sensível, protegido por
human-in-the-loop via `interrupt()` (retomado pelo cliente com `Command(resume=...)`).

A UI (cards/checkboxes/dialog) NÃO vive aqui — ela é renderizada por tools de frontend
genéricas (`web/frontend-tools.js` + `web/ui-components.js`). O agente busca os dados
aqui e os apresenta através daquelas tools de UI.
"""

import json
from datetime import date

from langchain_core.tools import tool
from langgraph.types import interrupt


# Fonte de verdade do cardápio (server-side). Trocar o domínio = trocar estes dados/tools.
_MENU = [
    {"id": "bruschetta", "name": "Bruschetta", "description": "Pão italiano, tomate e manjericão", "price": 28.0},
    {"id": "risoto", "name": "Risoto de Funghi", "description": "Arroz arbóreo e cogumelos", "price": 48.0},
    {"id": "salmao", "name": "Salmão Grelhado", "description": "Com legumes salteados", "price": 62.0},
    {"id": "massa", "name": "Massa ao Pesto", "description": "Talharim com molho pesto", "price": 39.0},
    {"id": "tiramisu", "name": "Tiramisù", "description": "Sobremesa clássica italiana", "price": 22.0},
]

_MENU_BY_ID = {item["id"]: item for item in _MENU}


@tool
def get_menu() -> str:
    """Return the restaurant menu (dishes with id, name, description and price).

    Use this tool when the user wants to see the menu or pick dishes. After getting the
    menu, present the dishes to the user with the frontend card-list tool so they can
    select; do not just paste the raw list as text.

    Returns a JSON array of objects: {id, name, description, price}.
    """
    return json.dumps(_MENU, ensure_ascii=False)


@tool
def get_available_times(date_iso: str) -> str:
    """Return the available reservation time slots for a given date.

    Use this tool when the user wants to book a table and a date is known. Present the
    returned slots to the user with the frontend option-list tool to let them choose.

    Input:
    - date_iso: the reservation date in ISO format (YYYY-MM-DD).

    Returns a JSON array of time strings (HH:MM). May be empty if the date is in the past.
    """
    try:
        day = date.fromisoformat(date_iso.strip())
    except ValueError:
        raise ValueError(f"Invalid date: '{date_iso}'. Use ISO format YYYY-MM-DD.")

    if day < date.today():
        return json.dumps([], ensure_ascii=False)

    # Horários fixos de demonstração (almoço e jantar).
    slots = ["12:00", "12:30", "13:00", "19:00", "19:30", "20:00", "20:30", "21:00"]
    return json.dumps(slots, ensure_ascii=False)


@tool
def create_reservation(
    customer_name: str,
    date_iso: str,
    time: str,
    party_size: int,
    item_ids: list[str],
) -> str:
    """Create a table reservation. Requires human approval before confirming (HITL).

    Use this tool only after the user has chosen a date, a time, the party size and
    (optionally) the dishes. Execution pauses automatically for the user to approve or
    reject; consider the reservation made only after approval.

    Input:
    - customer_name: name for the reservation.
    - date_iso: reservation date in ISO format (YYYY-MM-DD).
    - time: reservation time (HH:MM).
    - party_size: number of people.
    - item_ids: list of dish ids chosen (may be empty).

    Returns a confirmation that the reservation was created, or that it was cancelled.
    """
    dishes = [_MENU_BY_ID[i]["name"] for i in item_ids if i in _MENU_BY_ID]

    decision = interrupt(
        {
            "action": "create_reservation",
            "customerName": customer_name,
            "date": date_iso,
            "time": time,
            "partySize": party_size,
            "dishes": dishes,
            "question": f"Confirmar reserva para {customer_name} em {date_iso} às {time} ({party_size} pessoa(s))?",
        }
    )

    # O cliente pode retomar com um booleano ou com {"approved": bool}.
    if isinstance(decision, dict):
        approved = bool(decision.get("approved", False))
    else:
        approved = bool(decision)

    if approved:
        extra = f" Pratos: {', '.join(dishes)}." if dishes else ""
        return (
            f"Reserva confirmada para {customer_name} em {date_iso} às {time}, "
            f"{party_size} pessoa(s).{extra}"
        )
    return f"Reserva cancelada pelo usuário. Nada foi reservado para {customer_name}."
