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
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command, interrupt


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
def update_order(
    item_ids: list[str],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Set the customer's current order (shared state shown live in the order panel).

    Call this EVERY time the selection changes — right after the customer picks, adds or
    removes dishes (including selecting cards) — so the order panel stays in sync on screen.
    Pass the FULL list of chosen dish ids (this replaces the current order; pass an empty
    list to clear it).

    Input:
    - item_ids: the dish ids currently in the order.

    Returns a short confirmation; the updated order is emitted to the UI as shared state.
    """
    items = [
        {"name": _MENU_BY_ID[i]["name"], "price": _MENU_BY_ID[i]["price"]}
        for i in item_ids
        if i in _MENU_BY_ID
    ]
    total = round(sum(it["price"] for it in items), 2)
    return Command(
        update={
            "order": items,
            "messages": [
                ToolMessage(
                    content=f"Pedido atualizado: {len(items)} item(ns), total {total}.",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


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

    try:
        date_label = date.fromisoformat(date_iso.strip()).strftime("%d/%m/%Y")
    except ValueError:
        date_label = date_iso

    # Conteúdo do interrupt em linguagem do usuário (rótulos PT-BR, sem campos técnicos).
    # O front genérico mostra `question` em destaque e os demais campos como "Rótulo: valor".
    decision = interrupt(
        {
            "question": "Confirmar esta reserva?",
            "Cliente": customer_name,
            "Data": date_label,
            "Horário": time,
            "Pessoas": party_size,
            "Pratos": ", ".join(dishes) if dishes else "—",
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
