"""
OpenAI (ChatGPT) implementation of the LLM provider.
"""

import json

import httpx

from app.config import settings
from app.services.llm import LLMProvider, RECIPE_PROMPT


class OpenAIProvider(LLMProvider):
    def __init__(self):
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.base_url = "https://api.openai.com/v1"

    async def _call(self, prompt: str) -> str:
        """Make a chat completion request to OpenAI."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"]["content"].strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        return text

    async def parse_recipe(self, recipe_text: str) -> list[dict]:
        prompt = RECIPE_PROMPT.format(recipe_text=recipe_text)
        text = await self._call(prompt)
        parsed = json.loads(text)
        # Handle wrapped response
        if isinstance(parsed, dict) and "ingredients" in parsed:
            return parsed["ingredients"]
        return parsed

    async def parse_raw(self, prompt: str) -> dict:
        text = await self._call(prompt)
        return json.loads(text)
