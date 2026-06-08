import json

import pytest

from app.domain.restaurant import tools as r


def test_get_menu_returns_json_list():
    menu = json.loads(r.get_menu.invoke({}))
    assert isinstance(menu, list) and menu
    assert {"id", "name", "description", "price"} <= set(menu[0])


def test_get_available_times():
    slots = json.loads(r.get_available_times.invoke({"date_iso": "2999-01-01"}))
    assert isinstance(slots, list) and "12:00" in slots
    # Data passada → sem horários.
    assert json.loads(r.get_available_times.invoke({"date_iso": "2000-01-01"})) == []
    with pytest.raises(ValueError):
        r.get_available_times.invoke({"date_iso": "bad"})


def test_update_reservation_partial_merge():
    # Primeiro passo: define pratos (aninhados em reservation.items).
    cmd1 = r.update_reservation.func(
        state={}, tool_call_id="c1", item_ids=["risoto", "salmao"]
    )
    items = cmd1.update["reservation"]["items"]
    assert [it["name"] for it in items] == ["Risoto de Funghi", "Salmão Grelhado"]
    assert cmd1.update["delivery"] == {}  # fluxo único ativo
    # Segundo passo: adiciona detalhes mantendo os pratos (merge sobre o estado).
    state = {"reservation": cmd1.update["reservation"], "delivery": {}}
    cmd2 = r.update_reservation.func(
        state=state, tool_call_id="c2", date_iso="2026-07-10", time="20:00", party_size=4
    )
    res = cmd2.update["reservation"]
    assert res["date"] == "2026-07-10" and res["time"] == "20:00" and res["party_size"] == 4
    assert [it["name"] for it in res["items"]] == ["Risoto de Funghi", "Salmão Grelhado"]


def test_update_delivery_merge_and_clears_reservation():
    cmd = r.update_delivery.func(
        state={"reservation": {"date": "x"}}, tool_call_id="c1",
        item_ids=["massa"], customer_name="Bia", address="Rua 1, 100", phone="119999",
    )
    deliv = cmd.update["delivery"]
    assert [it["name"] for it in deliv["items"]] == ["Massa ao Pesto"]
    assert deliv["customer_name"] == "Bia" and deliv["address"] == "Rua 1, 100"
    assert cmd.update["reservation"] == {}  # ativar delivery zera a reserva


def test_create_reservation_hitl(monkeypatch):
    # Aprovado → Command que limpa AMBOS os rascunhos e confirma via ToolMessage.
    monkeypatch.setattr(r, "interrupt", lambda payload: True)
    out = r.create_reservation.func(
        tool_call_id="c1",
        customer_name="Ana", date_iso="2026-07-01", time="19:30", party_size=2, item_ids=["risoto"]
    )
    assert out.update["reservation"] == {} and out.update["delivery"] == {}
    assert "confirmada" in out.update["messages"][0].content.lower()
    # Recusado → string, rascunho preservado (sem update de estado).
    monkeypatch.setattr(r, "interrupt", lambda payload: False)
    out2 = r.create_reservation.func(
        tool_call_id="c2",
        customer_name="Ana", date_iso="2026-07-01", time="19:30", party_size=2, item_ids=[]
    )
    assert "cancelada" in out2.lower()


def test_create_delivery_order_hitl(monkeypatch):
    monkeypatch.setattr(r, "interrupt", lambda payload: True)
    out = r.create_delivery_order.func(
        tool_call_id="c1", customer_name="Bia", address="Rua 1, 100", phone="119999",
        item_ids=["massa"], notes="sem cebola",
    )
    assert out.update["reservation"] == {} and out.update["delivery"] == {}
    assert "confirmado" in out.update["messages"][0].content.lower()
    monkeypatch.setattr(r, "interrupt", lambda payload: False)
    out2 = r.create_delivery_order.func(
        tool_call_id="c2", customer_name="Bia", address="Rua 1, 100", phone="119999",
        item_ids=["massa"],
    )
    assert "cancelado" in out2.lower()
