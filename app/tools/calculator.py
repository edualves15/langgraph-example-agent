import ast
import operator as op

from langchain_core.tools import tool

_ALLOWED_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.USub: op.neg,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_eval(node.operand))
    raise ValueError("Expressão não permitida")


@tool
def calculator(expression: str) -> str:
    """Calcula expressões matemáticas simples, como '180 / 6' ou '(12 + 8) * 3'."""
    parsed = ast.parse(expression, mode="eval")
    result = _eval(parsed.body)
    return str(result)


calculator.metadata = {
    "step_label": "Calculando: {expression}",
    "step_done_label": "Cálculo concluído",
    "step_icon": "calculator",
    "step_category": "compute",
}
