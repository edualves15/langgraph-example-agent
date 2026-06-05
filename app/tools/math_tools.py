import ast
import operator as op
from typing import Union

from langchain_core.tools import tool


Number = Union[int, float]


ALLOWED_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}


# Teto de dígitos do resultado de uma potência inteira. Bloqueia "bombas" de
# magnitude (ex.: `9**9**9`, `((2**1000)**1000)**1000`) que travariam CPU/memória,
# sem afetar matemática normal (`2**10`, percentuais, `2**0.5`).
_MAX_POW_RESULT_DIGITS = 10000


def _guard_pow(base: Number, exponent: Number) -> None:
    """Recusa potências inteiras cujo resultado teria magnitude descomunal."""
    if isinstance(base, int) and isinstance(exponent, int) and exponent > 0:
        # nº de dígitos do resultado ≈ dígitos(base) * expoente.
        if (len(str(abs(base))) or 1) * exponent > _MAX_POW_RESULT_DIGITS:
            raise ValueError("Power result is too large to compute.")


def _safe_eval_math_node(node: ast.AST) -> Number:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value

    if isinstance(node, ast.BinOp):
        operator_type = type(node.op)
        if operator_type not in ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported operator: {operator_type.__name__}")
        left = _safe_eval_math_node(node.left)
        right = _safe_eval_math_node(node.right)
        if operator_type is ast.Pow:
            _guard_pow(left, right)
        return ALLOWED_OPERATORS[operator_type](left, right)

    if isinstance(node, ast.UnaryOp):
        operator_type = type(node.op)
        if operator_type not in ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported operator: {operator_type.__name__}")
        operand = _safe_eval_math_node(node.operand)
        return ALLOWED_OPERATORS[operator_type](operand)

    raise ValueError(f"Invalid mathematical expression: {type(node).__name__}")


@tool
def calculate_math_expression(expression: str) -> str:
    """
    Compute an exact arithmetic expression and return the numeric result.

    Use this tool when the user needs exact numeric computation: arithmetic,
    percentages, totals, differences, averages, multiplications, divisions, powers,
    modulo, financial calculations, or parenthesized multi-step math. Prefer it over
    computing mentally.

    Input:
    - expression: a pure arithmetic expression. Operators: + - * / // ** % , unary
      + -, and parentheses. Use "." as the decimal separator (not commas). Do NOT
      include words, units, currency symbols, variables, or functions such as sqrt(),
      sin(), cos(), log(), or abs().

    Good inputs: "25 * 4 + 10", "(1000 * 0.15) + 300", "((42 - 7) / 5) ** 2".

    Returns the computed numeric result as a string.
    """
    expression = expression.strip()

    if not expression:
        raise ValueError("The mathematical expression is empty.")

    if len(expression) > 500:
        raise ValueError("The mathematical expression is too long.")

    tree = ast.parse(expression, mode="eval")
    result = _safe_eval_math_node(tree.body)

    return str(result)
