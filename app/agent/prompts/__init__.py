"""Carregamento e composição do system prompt.

O texto **genérico** vive em `system.md` (copy separada do código, sem domínio). O
fragmento de **domínio** (papel/fluxos) vem do `Domain.prompt` e é concatenado aqui — o
engine não conhece o negócio, só compõe os dois pedaços. A data de hoje é injetada no
sentinela `{{TODAY}}` via `str.replace` — não usamos `str.format` para não conflitar com
chaves `{`/`}` ou crases que o Markdown possa conter.
"""

from datetime import date
from importlib.resources import files

_TEMPLATE = files(__package__).joinpath("system.md").read_text(encoding="utf-8").strip()


def get_system_prompt(domain_fragment: str = "") -> str:
    """Retorna o system prompt (genérico + fragmento de domínio) com a data de hoje.

    `domain_fragment` é o `Domain.prompt` (texto do negócio); quando vazio, o prompt
    permanece 100% genérico.
    """
    text = _TEMPLATE
    if domain_fragment and domain_fragment.strip():
        text = f"{text}\n\n{domain_fragment.strip()}"
    return text.replace("{{TODAY}}", date.today().strftime("%d/%m/%Y"))
