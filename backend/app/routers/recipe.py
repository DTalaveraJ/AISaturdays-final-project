"""
Recipe parsing endpoint — uses LLM to extract ingredients.
"""

from fastapi import APIRouter, HTTPException
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
    try:
        ingredients = await llm.parse_recipe(req.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM parsing failed: {str(e)}")

    return RecipeResponse(
        ingredients=[Ingredient(**ing) for ing in ingredients]
    )
