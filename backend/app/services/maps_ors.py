"""
OpenRouteService implementation of the maps provider (fallback).
"""

import httpx

from app.config import settings
from app.services.maps import GeocodedLocation, MapsProvider, RouteResult


class ORSMapsProvider(MapsProvider):
    BASE = "https://api.openrouteservice.org"

    def __init__(self):
        self.key = settings.ors_api_key

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

        # VRP optimization
        jobs = [
            {"id": i + 1, "location": [s["lng"], s["lat"]]}
            for i, s in enumerate(stops)
        ]
        async with httpx.AsyncClient() as client:
            vrp_resp = await client.post(
                f"{self.BASE}/optimization",
                json={
                    "jobs": jobs,
                    "vehicles": [{
                        "id": 1,
                        "profile": transport_mode,
                        "start": [home.lng, home.lat],
                        "end": [home.lng, home.lat],
                    }],
                },
                headers=headers,
            )
            vrp = vrp_resp.json()

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
        async with httpx.AsyncClient() as client:
            dir_resp = await client.post(
                f"{self.BASE}/v2/directions/{transport_mode}/geojson",
                json={"coordinates": coords},
                headers=headers,
            )
            directions = dir_resp.json()

        summary = directions["features"][0]["properties"]["summary"]
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
            polyline=None,
        )
