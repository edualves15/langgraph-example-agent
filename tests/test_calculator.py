from app.tools.calculator import calculator


def test_calculator():
    assert calculator.invoke({"expression": "180 / 6"}) == "30.0"
