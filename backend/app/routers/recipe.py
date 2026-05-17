"""
Recipe parsing endpoint — uses LLM to extract ingredients.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.factory import get_llm_provider

router = APIRouter()


class RecipeRequest(BaseModel):
    text: str  # recipe text or pasted content


class Ingredient(BaseModel):
    name: str
    quantity: str
    category: str


class RecipeResponse(BaseModel):
    ingredients: list[Ingredient]


@router.post("/parse", response_model=RecipeResponse)
async def parse_recipe(req: RecipeRequest):
    """Extract ingredients from recipe text using LLM."""
    llm = get_llm_provider()
    ingredients = await llm.parse_recipe(req.text)
    return RecipeResponse(
        ingredients=[Ingredient(**ing) for ing in ingredients]
    )
