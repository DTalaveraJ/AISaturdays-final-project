"""
LLM service abstraction for recipe parsing.
Supports Gemini and Ollama as backends.
Switch via LLM_PROVIDER env var ("gemini" or "ollama").
"""

from abc import ABC, abstractmethod

from app.config import settings


class LLMProvider(ABC):
    @abstractmethod
    async def parse_recipe(self, recipe_text: str) -> list[dict]:
        """
        Extract ingredients from recipe text.
        Returns list of {"name": str, "quantity": str, "category": str}
        """
        ...

    @abstractmethod
    async def parse_raw(self, prompt: str) -> dict:
        """
        Send a raw prompt expecting a JSON object response.
        Used for product matching, substitutions, etc.
        """
        ...


RECIPE_PROMPT = """Extract all ingredients from the following recipe text.
Return a JSON array where each element has:
- "name": the ingredient name in Spanish (e.g., "leche", "aceite de oliva")
- "quantity": the amount needed as a string (e.g., "500ml", "2 unidades", "1kg")
- "category": a general food category in Spanish (e.g., "lácteos", "aceites", "carnes")

Return ONLY the JSON array, no other text.

Recipe:
{recipe_text}"""
