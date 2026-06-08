"""Classificação de erros do servidor.

`describe_error` converte qualquer exceção em uma mensagem curta e **segura para o
cliente** — específica quando o tipo do erro é determinável (auth/cota/rede/5xx),
genérica caso contrário (sem expor texto cru da exceção, para não vazar detalhes
internos num endpoint sem auth). `error_hint` devolve uma pista (tipo + 1ª linha) para
uso **apenas no log do servidor**. Nenhuma das duas expõe traceback.
"""

from __future__ import annotations

_MAX_HINT = 160


def error_hint(exc: BaseException) -> str:
    """Pista curta para LOG do servidor: `Tipo: 1ª linha` (sem traceback)."""
    try:
        message = str(exc).strip()
        first_line = message.splitlines()[0][:_MAX_HINT] if message else ""
        return f"{type(exc).__name__}: {first_line}" if first_line else type(exc).__name__
    except Exception:
        return "UnknownError"


def _http_status(exc: BaseException) -> int | None:
    """Procura um código HTTP 4xx/5xx na cadeia de causas (profundidade limitada)."""
    current: BaseException | None = exc
    for _ in range(10):  # cadeia de causas é acíclica na prática; o teto evita surpresas
        if current is None:
            break
        for attr in ("status_code", "status", "code", "http_status"):
            value = getattr(current, attr, None)
            if isinstance(value, int) and 400 <= value < 600:
                return value
        current = current.__cause__ or current.__context__
    return None


def describe_error(exc: BaseException) -> str:
    """Mensagem **segura para o cliente**, sem traceback nem texto cru da exceção.

    Específica quando o erro é reconhecível (auth, cota, rede, indisponibilidade);
    genérica caso contrário. A pista detalhada (tipo/1ª linha) NÃO vai ao cliente —
    use `error_hint(exc)` para isso, só no log.
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

        # Genérico — SEM texto cru da exceção (evita info-disclosure ao cliente).
        # O detalhe vai ao log via error_hint().
        return "Erro inesperado ao processar a solicitação. Tente novamente."
    except Exception:
        # describe_error jamais deve falhar.
        return "Erro inesperado ao processar a solicitação."
