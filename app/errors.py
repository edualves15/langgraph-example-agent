"""Classificação de erros do servidor.

Converte qualquer exceção em uma mensagem curta e segura — específica quando o
tipo do erro é determinável, genérica (com uma pista) caso contrário. Nunca
expõe traceback. É usada tanto para o log (uma linha, sem stack trace) quanto
para a mensagem enviada ao cliente no evento AG-UI `RUN_ERROR`.
"""

from __future__ import annotations

_MAX_HINT = 160


def _http_status(exc: BaseException) -> int | None:
    """Procura um código HTTP 4xx/5xx na cadeia de causas da exceção."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for attr in ("status_code", "status", "code", "http_status"):
            value = getattr(current, attr, None)
            if isinstance(value, int) and 400 <= value < 600:
                return value
        current = current.__cause__ or current.__context__
    return None


def describe_error(exc: BaseException) -> str:
    """Mensagem segura e acionável para um erro, sem traceback.

    Específica quando o erro é reconhecível (auth, cota, rede, indisponibilidade);
    genérica + pista (tipo da exceção e 1ª linha da mensagem) quando não for.
    """
    try:
        status = _http_status(exc)
        if status == 429:
            return ("Limite de requisições do provedor de IA atingido. "
                    "Aguarde alguns instantes e tente novamente.")
        if status in (401, 403):
            return ("Falha de autenticação com o provedor de IA. "
                    "Verifique a chave de API configurada (GEMINI_API_KEY).")
        if status == 400:
            return "A solicitação ao provedor de IA foi rejeitada (requisição inválida)."
        if status is not None and 500 <= status < 600:
            return ("O provedor de IA está temporariamente indisponível. "
                    "Tente novamente em breve.")

        name = type(exc).__name__.lower()
        if any(k in name for k in ("timeout", "timedout", "deadline")):
            return ("Tempo limite ao contatar o provedor de IA. "
                    "Verifique a conexão e tente novamente.")
        if any(k in name for k in ("connect", "connection", "network", "dns", "resolve", "ssl")):
            return ("Não foi possível conectar ao provedor de IA. "
                    "Verifique a conexão de rede.")

        # Genérico — inclui uma pista (tipo + 1ª linha da mensagem), sem traceback.
        first_line = ""
        message = str(exc).strip()
        if message:
            first_line = message.splitlines()[0][:_MAX_HINT]
        hint = f"{type(exc).__name__}: {first_line}" if first_line else type(exc).__name__
        return f"Erro inesperado ao processar a solicitação. Pista: {hint}"
    except Exception:
        # describe_error jamais deve falhar.
        return "Erro inesperado ao processar a solicitação."
