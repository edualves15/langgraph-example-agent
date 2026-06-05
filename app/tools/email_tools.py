"""Ferramenta de backend com efeito server-side + human-in-the-loop.

`send_email` é executada **no servidor** (efeito real) e usa `interrupt()` do
LangGraph para pausar a execução e aguardar a aprovação do usuário, retomada pelo
cliente via `Command(resume=...)`. É o exemplo canônico de uma tool que pertence ao
backend (diferente de uma tool de frontend, que o cliente anuncia em runtime e
executa no navegador — ver `web/frontend-tools.js`).
"""

from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email. Requires human approval before sending (human-in-the-loop).

    Use this tool when the user asks to send an email. Draft the full email yourself
    (recipient, subject, body) from the request — do not stop to ask for details you
    can reasonably infer. Execution pauses automatically for the user to approve or
    reject; consider the email sent only after approval.

    Input:
    - to: recipient email address.
    - subject: the subject line.
    - body: the full email body.

    Returns a confirmation that the email was sent, or that the user cancelled it.
    """
    decision = interrupt(
        {
            "action": "send_email",
            "to": to,
            "subject": subject,
            "body": body,
            "question": f"Enviar este e-mail para {to}?",
        }
    )

    # O cliente pode retomar com um booleano ou com {"approved": bool}.
    if isinstance(decision, dict):
        approved = bool(decision.get("approved", False))
    else:
        approved = bool(decision)

    if approved:
        return f"E-mail enviado para {to} com o assunto '{subject}'."
    return f"Envio cancelado pelo usuário. O e-mail para {to} NÃO foi enviado."
