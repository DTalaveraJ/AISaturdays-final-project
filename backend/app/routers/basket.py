"""
Basket optimization endpoint — with optional LLM-powered product matching.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_db
from app.services.factory import get_llm_provider
from app.services.product_matcher import ProductMatcher

router = APIRouter()


class BasketRequest(BaseModel):
    categories: list[str]
    budget: float = 50.0
    n_people: int = 1
    max_shops: int = 3
    store_ids: list[str] | None = None  # optional filter to specific stores
    smart_match: bool = False  # set True to use LLM filtering (slower but more accurate)


class BasketItem(BaseModel):
    store_id: str
    store_name: str
    product_name: str
    unit_price: float
    quantity: int
    line_total: float


class Suggestion(BaseModel):
    category: str
    product_id: str
    product_name: str
    reason: str


class BasketResponse(BaseModel):
    items: list[BasketItem]
    total_cost: float
    stores_used: list[str]
    suggestions: list[Suggestion] = []  # substitution suggestions for unmatched items


def _query_products_for_category(keyword: str, store_ids: list[str] | None = None):
    """Query products matching a keyword, returning up to 30 for LLM ranking."""
    with get_db() as conn:
        cur = conn.cursor()
        kw = f"%{keyword.lower()}%"

        if store_ids:
            cur.execute(
                """
                SELECT DISTINCT ON (p.id)
                       p.id AS product_id, p.name, ps.price,
                       s.id AS store_id, s.name AS store_name
                FROM products p
                JOIN price_snapshots ps ON ps.product_id = p.id
                JOIN stores s ON p.store_id = s.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE (LOWER(p.name) LIKE %s OR LOWER(c.slug) LIKE %s
                       OR LOWER(c.name) LIKE %s)
                  AND s.id = ANY(%s::uuid[])
                ORDER BY p.id, ps.scraped_at DESC
                """,
                (kw, kw, kw, store_ids),
            )
        else:
            cur.execute(
                """
                SELECT DISTINCT ON (p.id)
                       p.id AS product_id, p.name, ps.price,
                       s.id AS store_id, s.name AS store_name
                FROM products p
                JOIN price_snapshots ps ON ps.product_id = p.id
                JOIN stores s ON p.store_id = s.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE LOWER(p.name) LIKE %s OR LOWER(c.slug) LIKE %s
                       OR LOWER(c.name) LIKE %s
                ORDER BY p.id, ps.scraped_at DESC
                """,
                (kw, kw, kw),
            )

        rows = cur.fetchall()

    results = [dict(r) for r in rows]
    results.sort(key=lambda r: float(r["price"]))
    return results[:30]


@router.post("/optimize", response_model=BasketResponse)
async def optimize_basket(req: BasketRequest):
    """
    Basket optimizer with optional LLM-powered product matching.
    When smart_match=True, uses LLM to filter irrelevant results and suggest substitutions.
    When smart_match=False, uses simple keyword matching (faster, no LLM cost).
    """
    try:
        return await _do_optimize(req)
    except Exception as e:
        print(f"[Basket] 💥 Unhandled error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Basket optimization failed: {str(e)}")


async def _do_optimize(req: BasketRequest) -> BasketResponse:
    import asyncio

    matcher = None
    if req.smart_match:
        print(f"\n[Basket] 🧠 Smart match ENABLED — using LLM to filter products")
        try:
            llm = get_llm_provider()
            matcher = ProductMatcher(llm)
            print(f"[Basket] ✅ LLM provider loaded: {type(llm).__name__}")
        except Exception as e:
            print(f"[Basket] ⚠ LLM unavailable, falling back to keyword matching: {e}")
            matcher = None
    else:
        print(f"\n[Basket] ⚡ Smart match DISABLED — using keyword matching only (no AI)")

    # Step 1: Query DB for all categories (fast, no LLM)
    raw_by_cat: dict[str, list[dict]] = {}
    for cat in req.categories:
        raw_results = _query_products_for_category(cat, req.store_ids)
        raw_by_cat[cat] = raw_results

    # Step 2: LLM matching (if enabled)
    candidates: dict[str, list[dict]] = {}
    suggestions: list[Suggestion] = []

    if matcher:
        # Process all categories through LLM — run concurrently for speed
        async def match_one(cat: str, raw_results: list[dict]):
            if not raw_results:
                return cat, None, Suggestion(
                    category=cat, product_id="", product_name="",
                    reason=f"No se encontraron productos para '{cat}' en las tiendas disponibles",
                )
            try:
                match_result = await asyncio.wait_for(
                    matcher.match_products(cat, raw_results),
                    timeout=60.0,  # 60s max per category
                )
                return cat, match_result, None
            except asyncio.TimeoutError:
                print(f"[Basket] ⏱️ Timeout for '{cat}' — falling back to keyword match")
                return cat, None, None
            except Exception as e:
                print(f"[Basket] ⚠ Smart match failed for '{cat}': {e}")
                return cat, None, None

        # Ollama is single-threaded — run sequentially to avoid queue starvation
        # Gemini/OpenAI handle concurrency fine — run in parallel
        from app.config import settings
        if settings.llm_provider == "ollama":
            print(f"[Basket] 🐌 Ollama detected — processing {len(req.categories)} categories sequentially")
            results = []
            for cat in req.categories:
                result = await match_one(cat, raw_by_cat[cat])
                results.append(result)
        else:
            print(f"[Basket] ⚡ Cloud LLM — processing {len(req.categories)} categories in parallel")
            tasks = [match_one(cat, raw_by_cat[cat]) for cat in req.categories]
            results = await asyncio.gather(*tasks)

        for cat, match_result, suggestion in results:
            raw_results = raw_by_cat[cat]

            if suggestion:
                suggestions.append(suggestion)
                continue

            if match_result is None:
                # LLM failed, fall back to raw results
                if raw_results:
                    candidates[cat] = raw_results[:10]
                continue

            if match_result.get("no_exact_match"):
                sug = match_result.get("suggestion")
                if sug:
                    suggestions.append(Suggestion(
                        category=cat,
                        product_id=sug.get("product_id", ""),
                        product_name=sug.get("name", ""),
                        reason=sug.get("reason", "Producto alternativo sugerido"),
                    ))
                    matched_ids = {sug["product_id"]}
                    filtered = [r for r in raw_results if str(r["product_id"]) in matched_ids]
                    if filtered:
                        candidates[cat] = filtered
                continue

            matched_ids = {m["product_id"] for m in match_result.get("matches", [])}
            filtered = [r for r in raw_results if str(r["product_id"]) in matched_ids]
            candidates[cat] = filtered if filtered else raw_results[:10]
    else:
        for cat in req.categories:
            raw_results = raw_by_cat[cat]
            if not raw_results:
                suggestions.append(Suggestion(
                    category=cat, product_id="", product_name="",
                    reason=f"No se encontraron productos para '{cat}' en las tiendas disponibles",
                ))
            else:
                candidates[cat] = raw_results[:10]

    # Greedy optimizer: cheapest product per category, fewest stores
    selected_shops: set = set()
    items: list[BasketItem] = []

    ordered_cats = sorted(candidates, key=lambda c: len(candidates[c]))

    for cat in ordered_cats:
        rows = candidates[cat]
        if not rows:
            continue
        match = next((r for r in rows if str(r["store_id"]) in selected_shops), None)
        if match is None:
            if len(selected_shops) < req.max_shops:
                match = rows[0]
            else:
                match = next(
                    (r for r in rows if str(r["store_id"]) in selected_shops),
                    rows[0],
                )
        selected_shops.add(str(match["store_id"]))
        qty = req.n_people if float(match["price"]) < 3.0 else 1
        items.append(BasketItem(
            store_id=str(match["store_id"]),
            store_name=match["store_name"] or "Unknown",
            product_name=match["name"],
            unit_price=float(match["price"]),
            quantity=qty,
            line_total=round(float(match["price"]) * qty, 2),
        ))

    total = round(sum(i.line_total for i in items), 2)

    return BasketResponse(
        items=items,
        total_cost=total,
        stores_used=list(selected_shops),
        suggestions=suggestions,
    )
