"""Carregamento do system prompt.

O texto vive em `system.md` (copy separada do código). A data de hoje é injetada
no sentinela `{{TODAY}}` via `str.replace` — não usamos `str.format` para não
conflitar com chaves `{`/`}` ou crases que o Markdown possa conter.
"""

from datetime import date
from importlib.resources import files

_TEMPLATE = files(__package__).joinpath("system.md").read_text(encoding="utf-8").strip()


def get_system_prompt() -> str:
    """Retorna o system prompt com a data de hoje atualizada."""
    return _TEMPLATE.replace("{{TODAY}}", date.today().strftime("%d/%m/%Y"))
