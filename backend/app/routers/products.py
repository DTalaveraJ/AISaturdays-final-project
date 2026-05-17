"""
Product search endpoints.
"""

from fastapi import APIRouter, Query

from app.db import get_db

router = APIRouter()


@router.get("/search")
def search_products(
    q: str = Query(..., description="Search keyword"),
    store_ids: str = Query(None, description="Comma-separated store UUIDs to filter"),
    limit: int = Query(20, description="Max results"),
):
    """
    Search products by name or category, returning latest price.
    Optionally filter by specific stores.
    """
    with get_db() as conn:
        cur = conn.cursor()
        keyword = f"%{q.lower()}%"

        if store_ids:
            ids = [s.strip() for s in store_ids.split(",")]
            cur.execute(
                """
                SELECT DISTINCT ON (p.id)
                       p.id, p.name, p.barcode, p.brand,
                       ps.price, ps.is_promo,
                       s.id AS store_id, s.name AS store_name, s.chain,
                       c.name AS category_name
                FROM products p
                JOIN price_snapshots ps ON ps.product_id = p.id
                JOIN stores s ON p.store_id = s.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE (LOWER(p.name) LIKE %s OR LOWER(c.name) LIKE %s)
                  AND s.id = ANY(%s::uuid[])
                ORDER BY p.id, ps.scraped_at DESC
                """,
                (keyword, keyword, ids),
            )
        else:
            cur.execute(
                """
                SELECT DISTINCT ON (p.id)
                       p.id, p.name, p.barcode, p.brand,
                       ps.price, ps.is_promo,
                       s.id AS store_id, s.name AS store_name, s.chain,
                       c.name AS category_name
                FROM products p
                JOIN price_snapshots ps ON ps.product_id = p.id
                JOIN stores s ON p.store_id = s.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE LOWER(p.name) LIKE %s OR LOWER(c.name) LIKE %s
                ORDER BY p.id, ps.scraped_at DESC
                """,
                (keyword, keyword),
            )

        rows = cur.fetchall()

    results = [dict(r) for r in rows]
    results.sort(key=lambda r: float(r["price"]))
    return results[:limit]


@router.get("/categories")
def list_categories():
    """List all product categories."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, slug, name FROM categories ORDER BY name")
        return [dict(r) for r in cur.fetchall()]
