from langchain_core.language_models.chat_models import BaseChatModel

from app.config import settings


def get_llm() -> BaseChatModel:
    """Cria o chat model do agente.

    Mantenha a troca de provider concentrada aqui para evitar lock-in.
    """
    provider = settings.llm_provider.lower().strip()

    if provider == "gemini":
        # Pacote recomendado pela integração LangChain para Gemini.
        # Instale também: pip install langchain-google-genai
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=0,
        )

    if provider == "proprietary":
        # Para API proprietária compatível com OpenAI.
        # Instale também: pip install langchain-openai
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.proprietary_model,
            api_key=settings.proprietary_api_key,
            base_url=settings.proprietary_base_url,
            temperature=0,
        )

    raise ValueError(f"LLM_PROVIDER inválido: {settings.llm_provider}")
