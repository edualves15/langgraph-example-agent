"""Ferramentas locais do agente.

As ferramentas são definidas como `@tool` do `langchain_core` e registradas em
`app.registries.tool_registry.get_local_tools()`. O streaming de cada chamada de
ferramenta é emitido nativamente como eventos AG-UI (`TOOL_CALL_START`/`ARGS`/
`END`/`RESULT`) pela integração oficial `ag_ui_langgraph`, sem metadados extras.
"""
