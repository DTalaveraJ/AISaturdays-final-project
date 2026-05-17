"""
Basket optimization endpoint — reuses Agent 1 logic.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.db import get_db

router = APIRouter()


class BasketRequest(BaseModel):
    categories: list[str]
    budget: float = 50.0
    n_people: int = 1
    max_shops: int = 3
    store_ids: list[str] | None = None  # optional filter to specific stores


class BasketItem(BaseModel):
    store_id: str
    store_name: str
    product_name: str
    unit_price: float
    quantity: int
    line_total: float


class BasketResponse(BaseModel):
    items: list[BasketItem]
    total_cost: float
    stores_used: list[str]


def _query_products_for_category(keyword: str, store_ids: list[str] | None = None):
    """Query cheapest products matching a keyword."""
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
    return results[:10]


@router.post("/optimize", response_model=BasketResponse)
def optimize_basket(req: BasketRequest):
    """
    Greedy basket optimizer: picks cheapest product per category,
    consolidating into fewest stores (up to max_shops).
    """
    candidates: dict[str, list[dict]] = {}
    for cat in req.categories:
        rows = _query_products_for_category(cat, req.store_ids)
        if rows:
            candidates[cat] = rows

    selected_shops: set = set()
    items: list[BasketItem] = []

    # Rarest categories first for better consolidation
    ordered_cats = sorted(candidates, key=lambda c: len(candidates[c]))

    for cat in ordered_cats:
        rows = candidates[cat]
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
    )
