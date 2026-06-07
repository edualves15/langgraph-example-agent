"""Dicas de apresentação do domínio para o front genérico, entregues em runtime via evento
AG-UI `CUSTOM` (`name="ui_hints"`, ver `app/routers/agent.py`) e usadas por `renderSummary`
em `web/app.js`. Sem elas, o front fica 100% genérico (rótulos humanizados / título "Resumo").
"""

# Ícone por chave (subcampo) de estado, exibido no resumo do fluxo ativo.
STATE_TAG_ICONS = {
    "items": "🍽️",
    "date": "📅",
    "time": "🕒",
    "party_size": "👥",
    "customer_name": "👤",
    "address": "📍",
    "phone": "☎️",
    "notes": "📝",
}

# Título do resumo por FLUXO (chave de topo do estado).
STATE_TITLES = {
    "reservation": "Sua reserva",
    "delivery": "Seu pedido",
}

# Estrutura entregue ao front (convenção do contrato Domain.ui_hints).
UI_HINTS = {
    "state_tag_icons": STATE_TAG_ICONS,
    "state_titles": STATE_TITLES,
}
