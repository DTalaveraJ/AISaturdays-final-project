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

# Spanish stop words ignored when tokenising multi-word ingredient queries
STOP_WORDS_ES = {"de", "del", "la", "el", "los", "las", "en", "con", "sin", "al", "a", "y", "o", "un", "una"}


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


def _rank_by_relevance(rows: list[dict], kw_lower: str) -> list[dict]:
    """Sort candidates so the product itself appears before products that merely contain it.

    Sort key: (tier, price_asc)
      Tier 0 — name starts with the full query  ("aceite de oliva virgen extra ...")
      Tier 1 — name starts with the first significant token  ("aceite ...")
      Tier 2 — all significant tokens present anywhere in name
      Tier 3 — partial match

    Without this, cheap products where the keyword is a secondary ingredient
    (e.g. "barra pan de aceite de oliva" at 0.57€) would crowd out the actual
    product ("aceite de oliva virgen extra" at 3.65€) in the top-10 seen by the LLM.
    """
    tokens = [t for t in kw_lower.split() if len(t) > 2 and t not in STOP_WORDS_ES]
    if not tokens:
        tokens = kw_lower.split()
    first = tokens[0] if tokens else kw_lower

    def tier(r: dict) -> int:
        name = r["name"].lower()
        if name.startswith(kw_lower):
            return 0
        if name.startswith(first):
            return 1
        if tokens and all(t in name for t in tokens):
            return 2
        return 3

    return sorted(rows, key=lambda r: (tier(r), float(r["price"])))


def _query_products_for_category(keyword: str, store_ids: list[str] | None = None):
    """Query products matching a keyword, returning up to 30 ranked by relevance.

    Multi-word queries (e.g. 'tiras pasta lasaña') are split into significant
    tokens, each searched separately, then results are merged and re-ranked.

    For short single keywords (≤4 chars) we use word-boundary matching to avoid
    false positives like 'sal' matching 'salchichas' or 'ensalada'.

    Results are sorted by relevance (name starts with query = most relevant) then
    price, so the actual product appears before cheaper items that merely mention
    the keyword as an ingredient.
    """
    kw_lower = keyword.lower().strip()
    tokens = kw_lower.split()

    if len(tokens) > 1:
        significant = [t for t in tokens if len(t) > 2 and t not in STOP_WORDS_ES]
        if not significant:
            significant = [max(tokens, key=len)]
        seen: set[str] = set()
        merged: list[dict] = []
        for token in significant:
            for row in _query_by_single_keyword(token, store_ids):
                pid = str(row["product_id"])
                if pid not in seen:
                    seen.add(pid)
                    merged.append(row)
        return _rank_by_relevance(merged, kw_lower)[:30]

    return _rank_by_relevance(_query_by_single_keyword(kw_lower, store_ids), kw_lower)[:30]


def _query_by_single_keyword(keyword: str, store_ids: list[str] | None = None):
    """Low-level DB query for a single keyword token."""
    with get_db() as conn:
        cur = conn.cursor()
        kw_lower = keyword.lower().strip()

        # Short words: require the keyword to appear as a whole word
        # (preceded/followed by space, digit boundary, or string start/end).
        # Longer words keep the original substring match.
        if len(kw_lower) <= 4:
            kw = f"% {kw_lower} %"          # surrounded by spaces (mid-string)
            kw_start = f"{kw_lower} %"       # at the very beginning
            kw_end = f"% {kw_lower}"         # at the very end
            exact = kw_lower                 # exact full match
            name_clause = (
                "LOWER(p.name) LIKE %s OR LOWER(p.name) LIKE %s "
                "OR LOWER(p.name) LIKE %s OR LOWER(p.name) = %s"
            )
            name_params = (kw, kw_start, kw_end, exact)
        else:
            kw = f"%{kw_lower}%"
            name_clause = "LOWER(p.name) LIKE %s"
            name_params = (kw,)

        cat_kw = f"%{kw_lower}%"

        if store_ids:
            cur.execute(
                f"""
                SELECT DISTINCT ON (p.id)
                       p.id AS product_id, p.name, ps.price,
                       s.id AS store_id, s.name AS store_name
                FROM products p
                JOIN price_snapshots ps ON ps.product_id = p.id
                JOIN stores s ON p.store_id = s.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE ({name_clause} OR LOWER(c.slug) LIKE %s OR LOWER(c.name) LIKE %s)
                  AND s.id = ANY(%s::uuid[])
                ORDER BY p.id, ps.scraped_at DESC
                """,
                (*name_params, cat_kw, cat_kw, store_ids),
            )
        else:
            cur.execute(
                f"""
                SELECT DISTINCT ON (p.id)
                       p.id AS product_id, p.name, ps.price,
                       s.id AS store_id, s.name AS store_name
                FROM products p
                JOIN price_snapshots ps ON ps.product_id = p.id
                JOIN stores s ON p.store_id = s.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE {name_clause} OR LOWER(c.slug) LIKE %s OR LOWER(c.name) LIKE %s
                ORDER BY p.id, ps.scraped_at DESC
                """,
                (*name_params, cat_kw, cat_kw),
            )

        rows = cur.fetchall()

    return [dict(r) for r in rows]


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
        # For sequential (Ollama) mode we track which store names are committed so far
        # and pass them to each LLM call — the prompt uses this to prefer consolidation.
        committed_store_names: list[str] = []

        async def match_one(cat: str, raw_results: list[dict], current_stores: list[str]):
            if not raw_results:
                return cat, None, Suggestion(
                    category=cat, product_id="", product_name="",
                    reason=f"No se encontraron productos para '{cat}' en las tiendas disponibles",
                )
            try:
                match_result = await asyncio.wait_for(
                    matcher.match_products(
                        cat, raw_results,
                        max_shops=req.max_shops,
                        selected_stores=current_stores,
                    ),
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
            # Sequential: pass the live committed-store list so the LLM sees which
            # stores are already in the basket before each call.
            print(f"[Basket] 🐌 Ollama detected — processing {len(req.categories)} categories sequentially")
            results = []
            for cat in req.categories:
                result = await match_one(cat, raw_by_cat[cat], list(committed_store_names))
                _, mr, _ = result
                if mr and not mr.get("no_exact_match"):
                    for m in mr.get("matches", []):
                        pid = m.get("product_id")
                        hit = next((r for r in raw_by_cat[cat] if str(r["product_id"]) == pid), None)
                        if hit and hit.get("store_name") not in committed_store_names:
                            committed_store_names.append(hit["store_name"])
                results.append(result)
        else:
            # Parallel: snapshot is empty at start — max_shops constraint still helps
            print(f"[Basket] ⚡ Cloud LLM — processing {len(req.categories)} categories in parallel")
            tasks = [match_one(cat, raw_by_cat[cat], list(committed_store_names)) for cat in req.categories]
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
                # suggestion is informational only — never add to basket candidates
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
                match = rows[0]  # open a new store — within budget
            else:
                # Hard limit reached: skip this category rather than violating max_shops
                suggestions.append(Suggestion(
                    category=cat, product_id="", product_name="",
                    reason=(
                        f"'{cat}' no disponible en las {req.max_shops} tiendas seleccionadas. "
                        "Aumenta el número máximo de tiendas para incluirlo."
                    ),
                ))
                continue
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
