"""Ferramentas de backend do domínio Restaurante.

São tools de **backend** (efeito/dado server-side): o cardápio e os horários são a
fonte de verdade no servidor; `create_reservation` é o efeito sensível, protegido por
human-in-the-loop via `interrupt()` (retomado pelo cliente com `Command(resume=...)`).

Parte do plug de domínio: registradas em `RESTAURANT_TOOLS` (`__init__.py`) → `Domain.tools`;
o estado que mutam (`reservation`/`delivery`) vive em `RestaurantState` (`state.py`).

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


def _items_from_ids(item_ids: list[str]) -> list[dict]:
    """Converte ids de pratos em itens padronizados `{name, price}` (ignora ids inválidos)."""
    return [
        {"name": _MENU_BY_ID[i]["name"], "price": _MENU_BY_ID[i]["price"]}
        for i in item_ids
        if i in _MENU_BY_ID
    ]


def _apply_fields(target: dict, fields: dict) -> dict:
    """Merge parcial do rascunho: grava em `target` só os campos com valor não-None."""
    for key, value in fields.items():
        if value is not None:
            target[key] = value
    return target


def _approved(decision) -> bool:
    """Normaliza a retomada do HITL: aceita booleano ou `{"approved": bool}`."""
    if isinstance(decision, dict):
        return bool(decision.get("approved", False))
    return bool(decision)


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
def update_reservation(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    item_ids: list[str] | None = None,
    date_iso: str | None = None,
    time: str | None = None,
    party_size: int | None = None,
    customer_name: str | None = None,
) -> Command:
    """Update the customer's current TABLE RESERVATION draft (shared state shown live).

    Call this EVERY time the customer makes or changes a reservation choice — picked dishes
    (incl. selecting cards), date, time, party size or name — passing ONLY the fields that
    changed. The draft is merged and shown live, so it always reflects everything chosen so
    far. For dishes, pass the FULL list of chosen ids (replaces the dishes; empty clears).

    Input (all optional; pass what changed):
    - item_ids: dish ids currently chosen.
    - date_iso: reservation date (YYYY-MM-DD).
    - time: reservation time (HH:MM).
    - party_size: number of people.
    - customer_name: name for the reservation.

    Returns a short confirmation; the merged draft is emitted to the UI as shared state.
    """
    reservation = dict(state.get("reservation") or {})
    if item_ids is not None:
        reservation["items"] = _items_from_ids(item_ids)
    _apply_fields(reservation, {
        "date": date_iso, "time": time,
        "party_size": party_size, "customer_name": customer_name,
    })

    # Um único fluxo ativo por vez: atualizar a reserva zera o rascunho de delivery.
    return Command(
        update={
            "reservation": reservation,
            "delivery": {},
            "messages": [ToolMessage(content="Reserva atualizada.", tool_call_id=tool_call_id)],
        }
    )


@tool
def update_delivery(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    item_ids: list[str] | None = None,
    customer_name: str | None = None,
    address: str | None = None,
    phone: str | None = None,
    notes: str | None = None,
) -> Command:
    """Update the customer's current DELIVERY ORDER draft (shared state shown live).

    Call this EVERY time the customer makes or changes a delivery choice — picked dishes
    (incl. selecting cards), name, address, phone or notes — passing ONLY the fields that
    changed. The draft is merged and shown live. For dishes, pass the FULL list of chosen
    ids (replaces the dishes; empty clears).

    Input (all optional; pass what changed):
    - item_ids: dish ids currently chosen.
    - customer_name: name for the order.
    - address: delivery address.
    - phone: contact phone.
    - notes: free-text notes (e.g. "no onions", reference point).

    Returns a short confirmation; the merged draft is emitted to the UI as shared state.
    """
    delivery = dict(state.get("delivery") or {})
    if item_ids is not None:
        delivery["items"] = _items_from_ids(item_ids)
    _apply_fields(delivery, {
        "customer_name": customer_name, "address": address,
        "phone": phone, "notes": notes,
    })

    # Um único fluxo ativo por vez: atualizar o delivery zera o rascunho de reserva.
    return Command(
        update={
            "delivery": delivery,
            "reservation": {},
            "messages": [ToolMessage(content="Pedido atualizado.", tool_call_id=tool_call_id)],
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
    tool_call_id: Annotated[str, InjectedToolCallId],
    customer_name: str,
    date_iso: str,
    time: str,
    party_size: int,
    item_ids: list[str],
) -> Command | str:
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

    if _approved(decision):
        extra = f" Pratos: {', '.join(dishes)}." if dishes else ""
        confirmation = (
            f"Reserva confirmada para {customer_name} em {date_iso} às {time}, "
            f"{party_size} pessoa(s).{extra}"
        )
        # Concluída → zera os rascunhos compartilhados para o próximo fluxo começar limpo
        # (o painel/popover zera via STATE_SNAPSHOT/DELTA; reducer default = overwrite).
        return Command(
            update={
                "reservation": {},
                "delivery": {},
                "messages": [ToolMessage(content=confirmation, tool_call_id=tool_call_id)],
            }
        )
    # Rejeitado: mantém o rascunho para o usuário ajustar (sem mexer no estado).
    return f"Reserva cancelada pelo usuário. Nada foi reservado para {customer_name}."


@tool
def create_delivery_order(
    tool_call_id: Annotated[str, InjectedToolCallId],
    customer_name: str,
    address: str,
    phone: str,
    item_ids: list[str],
    notes: str | None = None,
) -> Command | str:
    """Place a delivery order. Requires human approval before confirming (HITL).

    Use this tool only after the user has chosen the dishes and provided name, address and
    phone. Execution pauses automatically for the user to approve or reject; consider the
    order placed only after approval.

    Input:
    - customer_name: name for the order.
    - address: delivery address.
    - phone: contact phone.
    - item_ids: list of dish ids chosen (must not be empty).
    - notes: optional free-text notes.

    Returns a confirmation that the order was placed, or that it was cancelled.
    """
    dishes = [_MENU_BY_ID[i]["name"] for i in item_ids if i in _MENU_BY_ID]

    decision = interrupt(
        {
            "question": "Confirmar este pedido para delivery?",
            "Cliente": customer_name,
            "Endereço": address,
            "Telefone": phone,
            "Pratos": ", ".join(dishes) if dishes else "—",
            "Observações": notes or "—",
        }
    )

    if _approved(decision):
        note = f" Obs.: {notes}." if notes else ""
        confirmation = (
            f"Pedido confirmado para {customer_name} — entrega em {address}, "
            f"tel. {phone}. Pratos: {', '.join(dishes)}.{note}"
        )
        return Command(
            update={
                "reservation": {},
                "delivery": {},
                "messages": [ToolMessage(content=confirmation, tool_call_id=tool_call_id)],
            }
        )
    return f"Pedido cancelado pelo usuário. Nada foi pedido para {customer_name}."
