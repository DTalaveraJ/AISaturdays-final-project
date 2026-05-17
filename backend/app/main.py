"""
FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import stores, products, basket, route, recipe

app = FastAPI(
    title="IAbuela API",
    description="Grocery optimization backend for Tu IAbuela de Confianza",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stores.router, prefix="/api/stores", tags=["stores"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(basket.router, prefix="/api/basket", tags=["basket"])
app.include_router(route.router, prefix="/api/route", tags=["route"])
app.include_router(recipe.router, prefix="/api/recipe", tags=["recipe"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
