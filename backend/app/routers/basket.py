"""
Basket optimization endpoint — with optional LLM-powered product matching.
"""

import math
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_db
from app.services.factory import get_llm_provider
from app.services.product_matcher import ProductMatcher

router = APIRouter()

# Average urban speeds (km/h) and default max round-trip times (min) per transport mode
TRANSPORT_SPEEDS_KMH = {
    "walking": 4.5,
    "bicycling": 15.0,
    "driving": 30.0,
    "transit": 20.0,
}
DEFAULT_MAX_ROUND_TRIP_MIN = {
    "walking": 60,
    "bicycling": 45,
    "driving": 90,
    "transit": 90,
}


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _one_way_min(
    lat1: float, lng1: float, lat2: float, lng2: float, transport_mode: str
) -> float:
    """Estimate one-way travel time in minutes (straight-line × 1.4 detour factor)."""
    dist_km = _haversine_km(lat1, lng1, lat2, lng2) * 1.4
    speed = TRANSPORT_SPEEDS_KMH.get(transport_mode, 20.0)
    return (dist_km / speed) * 60.0


class BasketRequest(BaseModel):
    categories: list[str]
    budget: float = 50.0
    n_people: int = 1
    max_shops: int = 3
    store_ids: list[str] | None = None
    smart_match: bool = False
    # Transport-aware optimization
    home_lat: float | None = None
    home_lng: float | None = None
    transport_mode: str = "driving"
    max_travel_time_min: float | None = None  # None → default per transport mode


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
    suggestions: list[Suggestion] = []
    estimated_travel_min: float | None = None


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
    except HTTPException:
        raise
    except BaseException as e:
        import traceback
        print(f"[Basket] 💥 Unhandled error: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Basket optimization failed: {type(e).__name__}: {e}")


async def _do_optimize(req: BasketRequest) -> BasketResponse:
    import asyncio

    # --- Proximity filtering ---
    # If home coords are provided, restrict to stores reachable within the time budget.
    effective_store_ids = req.store_ids
    store_one_way: dict[str, float] = {}  # store_id → estimated one-way minutes

    if req.home_lat is not None and req.home_lng is not None:
        max_rt = req.max_travel_time_min or DEFAULT_MAX_ROUND_TRIP_MIN.get(req.transport_mode, 90)

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, latitude, longitude FROM stores "
                "WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
            )
            store_rows = cur.fetchall()

        reachable: list[str] = []
        for r in store_rows:
            sid = str(r["id"])
            t = _one_way_min(
                req.home_lat, req.home_lng,
                float(r["latitude"]), float(r["longitude"]),
                req.transport_mode,
            )
            if t * 2 <= max_rt:
                reachable.append(sid)
                store_one_way[sid] = t

        if req.store_ids:
            effective_store_ids = [sid for sid in req.store_ids if sid in set(reachable)]
        else:
            effective_store_ids = reachable if reachable else None

        print(
            f"[Basket] 📍 {len(reachable)} stores reachable within "
            f"{max_rt:.0f} min round-trip ({req.transport_mode})"
        )

    # --- LLM setup ---
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
        raw_results = _query_products_for_category(cat, effective_store_ids)
        raw_by_cat[cat] = raw_results

    # Step 2: LLM matching (if enabled)
    candidates: dict[str, list[dict]] = {}
    suggestions: list[Suggestion] = []

    if matcher:
        async def match_one(cat: str, raw_results: list[dict]):
            if not raw_results:
                return cat, None, Suggestion(
                    category=cat, product_id="", product_name="",
                    reason=f"No se encontraron productos para '{cat}' en las tiendas disponibles",
                )
            try:
                match_result = await asyncio.wait_for(
                    matcher.match_products(cat, raw_results),
                    timeout=60.0,
                )
                return cat, match_result, None
            except asyncio.TimeoutError:
                print(f"[Basket] ⏱️ Timeout for '{cat}' — falling back to keyword match")
                return cat, None, None
            except Exception as e:
                print(f"[Basket] ⚠ Smart match failed for '{cat}': {e}")
                return cat, None, None

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

    # Estimate round-trip travel time through selected stores
    estimated_travel_min: float | None = None
    if store_one_way and selected_shops:
        times = [store_one_way[sid] for sid in selected_shops if sid in store_one_way]
        if times:
            estimated_travel_min = round(max(times) * 2, 0)

    return BasketResponse(
        items=items,
        total_cost=total,
        stores_used=list(selected_shops),
        suggestions=suggestions,
        estimated_travel_min=estimated_travel_min,
    )
