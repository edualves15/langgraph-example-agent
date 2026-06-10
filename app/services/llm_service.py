"""Único ponto do projeto que lida com o LLM.

Seleciona o provider pelo **nome** (`LLM_PROVIDER`) e devolve um `BaseChatModel`. O `.env`
guarda só o nome do provider (+ `LLM_API_KEY`/`LLM_BASE_URL` p/ ollama e custom); o **modelo
default por provider vive aqui** — para trocar de modelo, edite `_DEFAULT_MODELS`; para mudar
classe/pacote/flags de um provider, edite a linha dele em `_PROVIDERS`.

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

import importlib
from collections.abc import Callable
from dataclasses import dataclass

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


@dataclass(frozen=True)
class _Provider:
    """Tudo que varia entre os providers embutidos — o resto é genérico (_build_from_spec)."""

    extra: str  # nome do extra no pyproject (p/ a mensagem de erro de import)
    module: str  # módulo a importar (lazy)
    cls: str  # classe ChatModel dentro do módulo
    key_arg: str | None = None  # kwarg que recebe a chave; None = provider sem chave
    requires_key: bool = False  # True → fail-fast se a chave estiver vazia
    base_url_arg: bool = False  # True → repassa LLM_BASE_URL
    default_base_url: str | None = None  # usado quando base_url_arg e LLM_BASE_URL vazio


# Tabela declarativa dos embutidos: uma linha por provider (ver _build_from_spec).
_PROVIDERS: dict[str, _Provider] = {
    "google": _Provider(
        "google", "langchain_google_genai", "ChatGoogleGenerativeAI",
        key_arg="google_api_key", requires_key=True),
    "openai": _Provider(
        "openai", "langchain_openai", "ChatOpenAI",
        key_arg="api_key", requires_key=True, base_url_arg=True),
    "anthropic": _Provider(
        "anthropic", "langchain_anthropic", "ChatAnthropic",
        key_arg="api_key", requires_key=True),
    "ollama": _Provider(
        "ollama", "langchain_ollama", "ChatOllama",
        base_url_arg=True, default_base_url="http://localhost:11434"),
    # CUSTOM (nome desconhecido e NÃO cadastrado via register_provider): assume API
    # OpenAI-compatível — padrão de proxies corporativos. Para um wire não-OpenAI, cadastre
    # um provider próprio (ver register_provider).
    "custom": _Provider(
        "openai", "langchain_openai", "ChatOpenAI",
        key_arg="api_key", base_url_arg=True),
}

_ALIASES = {"gemini": "google"}


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


def _import(spec: _Provider) -> type[BaseChatModel]:
    try:
        module = importlib.import_module(spec.module)
    except ImportError as exc:
        raise _missing(spec.extra, exc) from exc
    return getattr(module, spec.cls)


def _build_from_spec(model_key: str, spec: _Provider) -> BaseChatModel:
    kwargs: dict = {"model": _DEFAULT_MODELS[model_key], "temperature": settings.llm_temperature}
    if spec.key_arg:
        kwargs[spec.key_arg] = (
            _require_key(model_key) if spec.requires_key else (settings.llm_api_key or "not-needed")
        )
    if spec.base_url_arg:
        kwargs["base_url"] = (settings.llm_base_url.strip() or None) or spec.default_base_url
    return _import(spec)(**kwargs)


def _build_model() -> BaseChatModel:
    name = settings.llm_provider.strip().lower()
    name = _ALIASES.get(name, name)

    # 1) Provider cadastrado pelo dev tem precedência (pode até sobrescrever um embutido).
    builder = _CUSTOM_PROVIDERS.get(name)
    if builder is not None:
        return builder()

    # 2) Embutido declarado na tabela. 3) Nome desconhecido → fallback OpenAI-compatível.
    spec = _PROVIDERS.get(name)
    if spec is not None:
        return _build_from_spec(name, spec)
    return _build_from_spec("custom", _PROVIDERS["custom"])


def get_llm() -> BaseChatModel:
    """Devolve o chat model do provider configurado (`LLM_PROVIDER`)."""
    return _build_model()
