"""
Application configuration loaded from environment variables.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = ""

    # Google Maps (swappable with ORS)
    google_maps_api_key: str = ""
    maps_provider: str = "google"  # "google" or "ors"
    ors_api_key: str = ""

    # LLM for recipe parsing (swappable)
    llm_provider: str = "gemini"  # "gemini" or "ollama"
    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # CORS
    frontend_url: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
