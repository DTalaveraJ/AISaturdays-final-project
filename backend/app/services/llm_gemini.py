"""
Gemini implementation of the LLM provider.
"""

import json

from google import genai

from app.config import settings
from app.services.llm import LLMProvider, RECIPE_PROMPT


class GeminiProvider(LLMProvider):
    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = "gemini-2.0-flash"

    async def parse_recipe(self, recipe_text: str) -> list[dict]:
        prompt = RECIPE_PROMPT.format(recipe_text=recipe_text)
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)
