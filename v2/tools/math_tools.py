import ast
import operator as op
from typing import Union

from langchain_core.tools import tool


# Tool design best practices are used here to maximize LLM understanding:
# - clear tool name
# - precise type hints
# - capability-focused docstring
# - explicit usage rules
# - concrete examples
# - safe implementation without eval()


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


def _safe_eval_math_node(node: ast.AST) -> Number:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value

    if isinstance(node, ast.BinOp):
        operator_type = type(node.op)

        if operator_type not in ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported operator: {operator_type.__name__}")

        left = _safe_eval_math_node(node.left)
        right = _safe_eval_math_node(node.right)

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
    Calculate exact mathematical expressions.

    Use this tool whenever the user asks for exact numeric computation,
    especially when the request includes:
    - arithmetic
    - percentages
    - totals
    - differences
    - averages
    - multiplications
    - divisions
    - powers
    - modulo operations
    - financial calculations
    - parenthesized multi-step calculations

    This tool is intended for deterministic math, not for general reasoning.

    Supported operations:
    - addition: 2 + 2
    - subtraction: 10 - 3
    - multiplication: 4 * 5
    - division: 20 / 4
    - floor division: 20 // 3
    - exponentiation: 2 ** 8
    - modulo: 10 % 3
    - unary signs: -5, +5
    - parentheses: (2 + 3) * 4

    Input requirements:
    - Provide only the mathematical expression.
    - Do not include natural language.
    - Do not include currency symbols.
    - Do not include units.
    - Do not include commas as decimal separators.
    - Use "." as the decimal separator.
    - Use "*" for multiplication.
    - Use "/" for division.
    - Use "**" for powers.
    - Do not use functions such as sqrt(), sin(), cos(), log(), or abs().
    - Do not use variables such as x, y, price, or total.

    Good inputs:
    - "25 * 4 + 10"
    - "(1000 * 0.15) + 300"
    - "((42 - 7) / 5) ** 2"

    Bad inputs:
    - "What is 25 times 4?"
    - "$100 + $20"
    - "10 reais + 5 reais"
    - "10,5 + 2"
    - "sqrt(16)"
    - "price * 0.2"

    Returns:
    - The computed numeric result as a string.
    """

    expression = expression.strip()

    if not expression:
        raise ValueError("The mathematical expression is empty.")

    if len(expression) > 500:
        raise ValueError("The mathematical expression is too long.")

    tree = ast.parse(expression, mode="eval")
    result = _safe_eval_math_node(tree.body)

    return str(result)


calculate_math_expression.metadata = {
    "step_label": "Calculando expressão matemática...",
    "step_label_template": "Calculando {expression}...",
    "step_done_label": "Cálculo concluído",
}