# langgraph-private-agent

Agente LangGraph exposto via **protocolo oficial AG-UI** (Agent-User Interaction),
usando a integração oficial `ag-ui-langgraph` e o cliente oficial `@ag-ui/client`.

- Endpoint AG-UI: `POST /agent` (SSE de eventos AG-UI canônicos).
- Página de demonstração (chat): abra `http://localhost:8000/` após subir o server.

```bash
pip install -e ".[dev]"
uvicorn app.main:app --port 8000
# abra http://localhost:8000/
```

Capacidades demonstradas: streaming de texto + lifecycle, tool calls + resultados,
estado compartilhado (`STATE_SNAPSHOT`/`STATE_DELTA`) e human-in-the-loop (interrupts).
Detalhes de arquitetura em `CLAUDE.md`.
