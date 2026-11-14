from langchain_gigachat import GigaChat

from src.core.config import Settings


def create_gigachat(settings: Settings) -> GigaChat:
    """Create a model from application settings without sending a request."""
    if settings.gigachat_auth_key is None:
        raise RuntimeError("Задайте GIGACHAT_AUTH_KEY в .env")

    return GigaChat(
        credentials=settings.gigachat_auth_key.get_secret_value(),
        scope="GIGACHAT_API_PERS",
        model=settings.gigachat_model,
        timeout=settings.gigachat_timeout_seconds,
        base_url="https://api.giga.chat/v1",
        max_tokens=100,
        verify_ssl_certs=True,
        ca_bundle_file=settings.gigachat_ca_bundle_file,
    )
