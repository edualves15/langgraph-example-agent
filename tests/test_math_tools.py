import time

import pytest

from app.tools.math_tools import calculate_math_expression as calc


def _run(expr: str) -> str:
    return calc.invoke({"expression": expr})


def test_basic_operators():
    assert _run("180 / 6") == "30.0"
    assert _run("2 ** 8") == "256"
    assert _run("(10 + 5) * 3") == "45"
    assert _run("17 % 5") == "2"
    assert _run("17 // 5") == "3"
    assert _run("-3 + 2") == "-1"
    assert _run("2 ** 0.5") == str(2 ** 0.5)


def test_errors_on_invalid_input():
    with pytest.raises(ValueError):
        _run("")
    with pytest.raises(ValueError):
        _run("x" * 501)  # acima do limite de comprimento
    with pytest.raises(ValueError):
        _run("abs(1)")  # chamadas de função não são permitidas
    with pytest.raises(ValueError):
        _run("__import__('os')")  # nomes/chamadas bloqueados
    with pytest.raises(ValueError):
        _run("1 & 2")  # operador bit-a-bit não suportado


def test_division_by_zero_raises():
    with pytest.raises(ZeroDivisionError):
        _run("1 / 0")


def test_power_dos_guard_is_fast():
    # Bombas de magnitude devem ser recusadas rapidamente (sem travar CPU/memória).
    for bomb in ("9**9**9", "((2**1000)**1000)**1000", "2**10000000"):
        start = time.time()
        with pytest.raises(ValueError):
            _run(bomb)
        assert time.time() - start < 1.0
