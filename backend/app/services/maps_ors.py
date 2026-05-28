"""
OpenRouteService implementation of the maps provider (fallback).
"""

import httpx


def _encode_polyline(coords: list[tuple[float, float]]) -> str:
    """Encode (lat, lng) pairs as a Google Maps encoded polyline string."""
    result = []
    prev_lat = prev_lng = 0
    for lat, lng in coords:
        for prev, cur in ((prev_lat, round(lat * 1e5)), (prev_lng, round(lng * 1e5))):
            delta = cur - prev
            delta = ~(delta << 1) if delta < 0 else delta << 1
            while delta >= 0x20:
                result.append(chr((0x20 | (delta & 0x1f)) + 63))
                delta >>= 5
            result.append(chr(delta + 63))
        prev_lat = round(lat * 1e5)
        prev_lng = round(lng * 1e5)
    return "".join(result)

from app.config import settings
from app.services.maps import GeocodedLocation, MapsProvider, RouteResult


_MODE_MAP = {
    "driving": "driving-car",
    "walking": "foot-walking",
    "bicycling": "cycling-regular",
    "transit": "driving-car",  # ORS has no transit; fall back to car
}


class ORSMapsProvider(MapsProvider):
    BASE = "https://api.openrouteservice.org"

    def __init__(self):
        self.key = settings.ors_api_key

    @staticmethod
    def _profile(transport_mode: str) -> str:
        return _MODE_MAP.get(transport_mode, transport_mode)

    async def geocode(self, address: str) -> GeocodedLocation | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE}/geocode/search",
                params={
                    "api_key": self.key,
                    "text": address,
                    "size": 1,
                    "boundary.country": "ES",
                    "lang": "es",
                },
                headers={"User-Agent": "IAbuela/2.0"},
            )
            data = resp.json()
        if not data.get("features"):
            return None
        feat = data["features"][0]
        lng, lat = feat["geometry"]["coordinates"]
        return GeocodedLocation(
            lat=lat, lng=lng,
            label=feat["properties"].get("label", address),
        )

    async def optimize_route(
        self,
        home: GeocodedLocation,
        stops: list[dict],
        transport_mode: str,
    ) -> RouteResult | None:
        if not stops:
            return None

        headers = {
            "Authorization": self.key,
            "Content-Type": "application/json",
        }

        profile = self._profile(transport_mode)

        # VRP optimization
        jobs = [
            {"id": i + 1, "location": [s["lng"], s["lat"]]}
            for i, s in enumerate(stops)
        ]
        async with httpx.AsyncClient(timeout=30.0) as client:
            vrp_resp = await client.post(
                f"{self.BASE}/optimization",
                json={
                    "jobs": jobs,
                    "vehicles": [{
                        "id": 1,
                        "profile": profile,
                        "start": [home.lng, home.lat],
                        "end": [home.lng, home.lat],
                    }],
                },
                headers=headers,
            )
            vrp = vrp_resp.json()

        if "routes" not in vrp:
            raise RuntimeError(f"ORS VRP error: {vrp}")

        ordered = []
        for step in vrp["routes"][0].get("steps", []):
            if step["type"] == "job":
                ordered.append(stops[step["id"] - 1])

        # Directions for distance/duration
        coords = (
            [[home.lng, home.lat]]
            + [[s["lng"], s["lat"]] for s in ordered]
            + [[home.lng, home.lat]]
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            dir_resp = await client.post(
                f"{self.BASE}/v2/directions/{profile}/geojson",
                json={"coordinates": coords},
                headers=headers,
            )
            directions = dir_resp.json()

        if "features" not in directions:
            raise RuntimeError(f"ORS directions error: {directions}")

        feature = directions["features"][0]
        summary = feature["properties"]["summary"]

        # Extract road-following geometry from GeoJSON (ORS returns [lng, lat])
        raw_coords = feature["geometry"]["coordinates"]
        polyline = _encode_polyline([(lat, lng) for lng, lat in raw_coords])

        home_stop = {"name": "🏠 Home", "lat": home.lat, "lng": home.lng}
        ordered_stops = (
            [home_stop]
            + [{"name": s.get("name", ""), "lat": s["lat"], "lng": s["lng"]} for s in ordered]
            + [home_stop]
        )

        return RouteResult(
            ordered_stops=ordered_stops,
            distance_km=round(summary["distance"] / 1000, 2),
            duration_min=round(summary["duration"] / 60, 1),
            polyline=polyline,
        )
