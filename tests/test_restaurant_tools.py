import json

import pytest

from app.tools import restaurant_tools as r


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
    # Primeiro passo: define pratos.
    cmd1 = r.update_reservation.func(
        state={}, tool_call_id="c1", item_ids=["risoto", "salmao"]
    )
    assert [it["name"] for it in cmd1.update["order"]] == ["Risoto de Funghi", "Salmão Grelhado"]
    # Segundo passo: adiciona detalhes SEM mexer nos pratos (merge sobre o estado).
    state = {"order": cmd1.update["order"], "reservation": {}}
    cmd2 = r.update_reservation.func(
        state=state, tool_call_id="c2", date_iso="2026-07-10", time="20:00", party_size=4
    )
    assert cmd2.update["reservation"] == {"date": "2026-07-10", "time": "20:00", "party_size": 4}
    assert "order" not in cmd2.update  # pratos não foram tocados


def test_create_reservation_hitl(monkeypatch):
    # Aprovado.
    monkeypatch.setattr(r, "interrupt", lambda payload: True)
    out = r.create_reservation.func(
        customer_name="Ana", date_iso="2026-07-01", time="19:30", party_size=2, item_ids=["risoto"]
    )
    assert "confirmada" in out.lower()
    # Recusado.
    monkeypatch.setattr(r, "interrupt", lambda payload: False)
    out2 = r.create_reservation.func(
        customer_name="Ana", date_iso="2026-07-01", time="19:30", party_size=2, item_ids=[]
    )
    assert "cancelada" in out2.lower()
