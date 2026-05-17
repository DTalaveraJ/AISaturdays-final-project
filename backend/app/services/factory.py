"""
Service factory — returns the correct provider based on config.
"""

from app.config import settings
from app.services.maps import MapsProvider
from app.services.llm import LLMProvider


def get_maps_provider() -> MapsProvider:
    if settings.maps_provider == "google":
        from app.services.maps_google import GoogleMapsProvider
        return GoogleMapsProvider()
    else:
        from app.services.maps_ors import ORSMapsProvider
        return ORSMapsProvider()


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "gemini":
        from app.services.llm_gemini import GeminiProvider
        return GeminiProvider()
    else:
        from app.services.llm_ollama import OllamaProvider
        return OllamaProvider()
