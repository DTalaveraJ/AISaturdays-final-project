"""
Store endpoints — find nearby stores, list by chain, etc.
"""

import math
from fastapi import APIRouter, Query

from app.db import get_db

router = APIRouter()


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance in km between two points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@router.get("/nearby")
def get_nearby_stores(
    lat: float = Query(..., description="User latitude"),
    lng: float = Query(..., description="User longitude"),
    radius_km: float = Query(10.0, description="Search radius in km"),
    limit: int = Query(20, description="Max results"),
):
    """Find stores near a given location, sorted by distance."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, chain, name, address, city, postcode,
                      latitude, longitude, opening_time, closing_time
               FROM stores
               WHERE latitude IS NOT NULL AND longitude IS NOT NULL"""
        )
        rows = cur.fetchall()

    results = []
    for row in rows:
        dist = _haversine(lat, lng, float(row["latitude"]), float(row["longitude"]))
        if dist <= radius_km:
            results.append({**dict(row), "distance_km": round(dist, 2)})

    results.sort(key=lambda x: x["distance_km"])
    return results[:limit]


@router.get("/chains")
def list_chains():
    """List all unique store chains."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT chain FROM stores ORDER BY chain")
        return [row["chain"] for row in cur.fetchall()]
