"""
Ollama implementation of the LLM provider (local fallback).
"""

import json

import httpx

from app.config import settings
from app.services.llm import LLMProvider, RECIPE_PROMPT


class OllamaProvider(LLMProvider):
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model

    async def parse_recipe(self, recipe_text: str) -> list[dict]:
        prompt = RECIPE_PROMPT.format(recipe_text=recipe_text)

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                    },
                )
                resp.raise_for_status()
            except httpx.ConnectError:
                raise RuntimeError(
                    f"Cannot connect to Ollama at {self.base_url}. "
                    "Is Ollama running? Start it with: ollama serve"
                )
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"Ollama returned {e.response.status_code}: {e.response.text}")

            data = resp.json()

        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")

        text = data.get("response", "").strip()
        if not text:
            raise RuntimeError("Ollama returned an empty response")

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"Ollama response is not valid JSON: {text[:200]}")

        # Ollama's "format": "json" always produces an object, never a bare array.
        # Extract the ingredient list from whatever key the model used.
        if isinstance(parsed, dict):
            for key in ("ingredients", "items", "result", "data", "lista", "productos"):
                if isinstance(parsed.get(key), list):
                    parsed = parsed[key]
                    break
            else:
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break

        if not isinstance(parsed, list):
            raise RuntimeError(f"Expected a JSON array, got: {type(parsed).__name__}")

        return parsed

    async def parse_raw(self, prompt: str) -> dict:
        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                    },
                )
                resp.raise_for_status()
            except httpx.ConnectError:
                raise RuntimeError(
                    f"Cannot connect to Ollama at {self.base_url}. "
                    "Is Ollama running? Start it with: ollama serve"
                )
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"Ollama returned {e.response.status_code}: {e.response.text}")

            data = resp.json()

        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")

        text = data.get("response", "").strip()
        if not text:
            raise RuntimeError("Ollama returned an empty response")

        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"Ollama response is not valid JSON: {text[:200]}")
