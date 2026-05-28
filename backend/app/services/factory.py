"""
Service factory — returns the correct provider based on config.
"""

from app.config import settings
from app.services.maps import MapsProvider
from app.services.llm import LLMProvider


def get_maps_provider(transport_mode: str = "") -> MapsProvider:
    # Transit always requires Google Maps (ORS has no transit support)
    if transport_mode == "transit":
        if not settings.google_maps_api_key or settings.google_maps_api_key == "your_google_maps_key":
            raise ValueError(
                "Transit directions require a Google Maps API key. "
                "Set GOOGLE_MAPS_API_KEY in backend/.env"
            )
        from app.services.maps_google import GoogleMapsProvider
        return GoogleMapsProvider()
    if settings.maps_provider == "google":
        from app.services.maps_google import GoogleMapsProvider
        return GoogleMapsProvider()
    from app.services.maps_ors import ORSMapsProvider
    return ORSMapsProvider()


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "gemini":
        from app.services.llm_gemini import GeminiProvider
        return GeminiProvider()
    elif settings.llm_provider == "openai":
        from app.services.llm_openai import OpenAIProvider
        return OpenAIProvider()
    else:
        from app.services.llm_ollama import OllamaProvider
        return OllamaProvider()
