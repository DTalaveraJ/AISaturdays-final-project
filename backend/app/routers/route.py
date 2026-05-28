"""
Route optimization endpoint.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_db
from app.services.factory import get_maps_provider
from app.services.maps import GeocodedLocation

router = APIRouter()


class RouteRequest(BaseModel):
    home_address: str | None = None
    home_lat: float | None = None
    home_lng: float | None = None
    store_ids: list[str]
    transport_mode: str = "driving"  # driving, walking, bicycling


class RouteStop(BaseModel):
    name: str
    lat: float
    lng: float
    address: str = ""


class TransitStepOut(BaseModel):
    mode: str
    instruction: str
    duration: str
    distance: str = ""
    line_name: str = ""
    vehicle_type: str = ""
    departure_stop: str = ""
    arrival_stop: str = ""
    num_stops: int = 0


class RouteResponse(BaseModel):
    ordered_stops: list[RouteStop]
    distance_km: float
    duration_min: float
    polyline: str | None = None
    transit_steps: list[TransitStepOut] = []


@router.post("/optimize", response_model=RouteResponse)
async def optimize_route(req: RouteRequest):
    """Compute optimal circular route: home → stores → home."""
    try:
        maps = get_maps_provider(req.transport_mode)

        # Resolve home coordinates
        if req.home_lat is not None and req.home_lng is not None:
            home = GeocodedLocation(lat=req.home_lat, lng=req.home_lng, label="Home")
        elif req.home_address:
            home = await maps.geocode(req.home_address)
            if not home:
                raise HTTPException(status_code=400, detail="Could not geocode home address")
        else:
            raise HTTPException(status_code=400, detail="Provide home_address or home_lat/home_lng")

        # Fetch store locations from DB
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT id, name, address, latitude, longitude
                   FROM stores WHERE id = ANY(%s::uuid[])""",
                (req.store_ids,),
            )
            rows = cur.fetchall()

        stops = [
            {
                "name": r["name"] or "Store",
                "address": r["address"] or "",
                "lat": float(r["latitude"]),
                "lng": float(r["longitude"]),
            }
            for r in rows
            if r["latitude"] is not None and r["longitude"] is not None
        ]

        if not stops:
            raise HTTPException(status_code=400, detail="No stores with valid coordinates found")

        result = await maps.optimize_route(home, stops, req.transport_mode)
        if not result:
            raise HTTPException(status_code=502, detail="Maps provider returned no result")

        return RouteResponse(
            ordered_stops=[
                RouteStop(name=s["name"], lat=s["lat"], lng=s["lng"], address=s.get("address", ""))
                for s in result.ordered_stops
            ],
            distance_km=result.distance_km,
            duration_min=result.duration_min,
            polyline=result.polyline,
            transit_steps=[
                TransitStepOut(**{k: getattr(step, k) for k in TransitStepOut.model_fields})
                for step in (result.transit_steps or [])
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Route optimization failed: {str(e)}")
