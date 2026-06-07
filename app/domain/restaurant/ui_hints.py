"""Dicas de **apresentação** do domínio Restaurante para o frontend genérico.

O front (`web/`) é agnóstico de domínio: não conhece nomes de chaves de estado nem
títulos. Estes mapas são entregues a ele em runtime via evento AG-UI `CUSTOM`
(`name="ui_hints"`, emitido em `app/routers/agent.py`) e usados pelo resumo da reserva
(`renderSummary` em `web/app.js`). Sem eles (`{}`), o front continua 100% genérico
(cai em rótulos humanizados / título "Resumo").
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
