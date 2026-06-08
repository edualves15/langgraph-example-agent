"""Composição do system prompt: texto genérico (`system.md`) + fragmento de domínio
(`Domain.prompt`). A data entra no sentinela `{{TODAY}}` via `str.replace` (não `str.format`,
para não conflitar com `{`/`}` e crases do Markdown).
"""

from datetime import date
from importlib.resources import files

_TEMPLATE = files(__package__).joinpath("system.md").read_text(encoding="utf-8").strip()


def get_system_prompt(domain_fragment: str = "") -> str:
    """System prompt genérico + `domain_fragment` (vazio ⇒ 100% genérico) com a data de hoje."""
    text = _TEMPLATE
    if domain_fragment and domain_fragment.strip():
        text = f"{text}\n\n{domain_fragment.strip()}"
    return text.replace("{{TODAY}}", date.today().strftime("%d/%m/%Y"))
