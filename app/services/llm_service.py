"""Único ponto do projeto que lida com o LLM.

Seleciona o provider pelo **nome** (`LLM_PROVIDER`) e devolve um `BaseChatModel`. O `.env`
guarda só o nome do provider (+ `LLM_API_KEY`/`LLM_BASE_URL` p/ ollama e custom); o **modelo
default por provider vive aqui** — para trocar de modelo, edite `_DEFAULT_MODELS` ou o ramo
do provider.

Os pacotes de cada provider são **dependências opcionais** (extras do `pyproject.toml`): só o
do provider selecionado precisa estar instalado (import lazy + erro claro se faltar).

**Provider genérico (extensão):** além dos embutidos, o dev pode **cadastrar** um provider
próprio com `register_provider(name, builder)` — uma factory `() -> BaseChatModel`. O nome
registrado é consultado **antes** dos embutidos (pode até sobrescrevê-los) e tem precedência
sobre o fallback OpenAI-compatível. Registre no composition root (`app/main.py`), ou em
qualquer módulo importado por ele, antes do startup. Ex.:

    from langchain_cohere import ChatCohere
    from app.services.llm_service import register_provider
    register_provider("cohere", lambda: ChatCohere(model="command-r"))
"""

from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import settings

# Providers cadastrados em runtime pelo dev (name -> factory). Ver register_provider.
ProviderBuilder = Callable[[], BaseChatModel]
_CUSTOM_PROVIDERS: dict[str, ProviderBuilder] = {}


def register_provider(name: str, builder: ProviderBuilder) -> None:
    """Cadastra (ou sobrescreve) um provider pelo nome.

    `builder` é uma factory **sem argumentos** que devolve um `BaseChatModel` já configurado
    (use `settings` lá dentro se precisar de temperatura/base_url/chave). Consultado antes dos
    providers embutidos e do fallback OpenAI-compatível. Ative selecionando `LLM_PROVIDER=<name>`.
    """
    _CUSTOM_PROVIDERS[name.strip().lower()] = builder

# Modelo default por provider (o .env não carrega nome de modelo). Edite aqui.
_DEFAULT_MODELS = {
    "google": "gemini-3.1-flash-lite",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "ollama": "llama3.1",
    "custom": "gpt-4o-mini",  # placeholder p/ proxy OpenAI-compatível; ajuste no seu wrapper
}


def _missing(extra: str, exc: Exception) -> ImportError:
    return ImportError(
        f"Provider '{settings.llm_provider}' requer o pacote do extra '{extra}'. "
        f"Instale com: pip install 'my-agent[{extra}]'. Detalhe: {exc}"
    )


def _require_key(provider: str) -> str:
    key = settings.llm_api_key.strip()
    if not key:
        raise ValueError(
            f"LLM_API_KEY não configurada para o provider '{provider}'. "
            "Defina-a no ambiente ou no .env (ver .env.example)."
        )
    return key


def _build_model() -> BaseChatModel:
    provider = settings.llm_provider.strip().lower()
    temperature = settings.llm_temperature
    base_url = settings.llm_base_url.strip() or None

    # Provider cadastrado pelo dev tem precedência (pode até sobrescrever um embutido).
    builder = _CUSTOM_PROVIDERS.get(provider)
    if builder is not None:
        return builder()

    if provider in ("google", "gemini"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise _missing("google", exc) from exc
        return ChatGoogleGenerativeAI(
            model=_DEFAULT_MODELS["google"],
            google_api_key=_require_key("google"),
            temperature=temperature,
        )

    if provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise _missing("openai", exc) from exc
        return ChatOpenAI(
            model=_DEFAULT_MODELS["openai"],
            api_key=_require_key("openai"),
            base_url=base_url,
            temperature=temperature,
        )

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise _missing("anthropic", exc) from exc
        return ChatAnthropic(
            model=_DEFAULT_MODELS["anthropic"],
            api_key=_require_key("anthropic"),
            temperature=temperature,
        )

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise _missing("ollama", exc) from exc
        return ChatOllama(
            model=_DEFAULT_MODELS["ollama"],
            base_url=base_url or "http://localhost:11434",
            temperature=temperature,
        )

    # CUSTOM (nome desconhecido e NÃO cadastrado via register_provider): assume API
    # OpenAI-compatível — o padrão de mercado p/ proxies corporativos. `base_url`/`api_key` vêm
    # da config (nuláveis). Para um wire não-OpenAI, cadastre um provider próprio (ver topo).
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise _missing("openai", exc) from exc
    return ChatOpenAI(
        model=_DEFAULT_MODELS["custom"],
        api_key=settings.llm_api_key or "not-needed",
        base_url=base_url,
        temperature=temperature,
    )


def get_llm() -> BaseChatModel:
    """Devolve o chat model do provider configurado (`LLM_PROVIDER`)."""
    return _build_model()
