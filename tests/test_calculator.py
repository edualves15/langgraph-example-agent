from app.tools.math_tools import calculate_math_expression


def test_calculate_math_expression():
    assert calculate_math_expression.invoke({"expression": "180 / 6"}) == "30.0"
    assert calculate_math_expression.invoke({"expression": "2 ** 8"}) == "256"
    assert calculate_math_expression.invoke({"expression": "(10 + 5) * 3"}) == "45"
