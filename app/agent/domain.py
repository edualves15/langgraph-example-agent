"""Contrato `Domain` — o ponto de plugue do negócio no engine genérico.

O engine (`app/agent/graph.py`) é **agnóstico de domínio**: ele recebe um `Domain`
por injeção e nunca importa o restaurante (ou qualquer negócio) diretamente. Trocar de
domínio = montar outro `Domain` no composition root (`app/main.py`) — um único import.

Um `Domain` agrupa tudo que o engine precisa saber sobre o negócio:

- `name` — identificador legível (logs/diagnóstico).
- `tools` — tools de **backend** do domínio (executadas no servidor, no nó `tools`).
- `state_schema` — subclasse de `AgentState` com as chaves de estado do domínio
  (ex.: `reservation`/`delivery`). É o `state_schema` do `StateGraph`.
- `prompt` — fragmento de system prompt do domínio (papel/fluxos), concatenado ao
  prompt genérico em `get_system_prompt(...)`.
- `predict_state` — mapeamento opcional de `PredictState` (AG-UI): liga uma chave de
  estado ao argumento de uma tool, para a UI prever o estado a partir dos args em streaming.
- `ui_hints` — dicas **de apresentação** entregues ao front em runtime via evento
  `CUSTOM` (`name="ui_hints"`); o front é genérico e só usa o que vier daqui. Convenção:
  `{"state_tag_icons": {<subcampo>: <emoji>}, "state_titles": {<fluxo>: <título>}}`.
"""

from dataclasses import dataclass, field

from langchain_core.tools import BaseTool


@dataclass(frozen=True)
class Domain:
    name: str
    tools: list[BaseTool]
    state_schema: type
    prompt: str
    predict_state: list[dict] = field(default_factory=list)
    ui_hints: dict = field(default_factory=dict)
