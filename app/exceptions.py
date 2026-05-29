class AgentError(Exception):
    """Erro de domínio do agente — base para todos os erros classificados."""


class QuotaExceededError(AgentError):
    """Provider retornou 429 — cota da API excedida."""


class ProviderAuthError(AgentError):
    """Provider retornou 401/403 — credencial inválida ou sem permissão."""


class AgentRuntimeError(AgentError):
    """Erro inesperado durante a execução do grafo."""
