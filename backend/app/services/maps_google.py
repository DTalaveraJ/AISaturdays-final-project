"""
Google Maps implementation of the maps provider.
"""

import httpx

from app.config import settings
from app.services.maps import GeocodedLocation, MapsProvider, RouteResult


class GoogleMapsProvider(MapsProvider):
    BASE = "https://maps.googleapis.com/maps/api"

    def __init__(self):
        self.key = settings.google_maps_api_key

    async def geocode(self, address: str) -> GeocodedLocation | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE}/geocode/json",
                params={"address": address, "key": self.key, "region": "es"},
            )
            data = resp.json()
        if data["status"] != "OK" or not data["results"]:
            return None
        result = data["results"][0]
        loc = result["geometry"]["location"]
        return GeocodedLocation(
            lat=loc["lat"],
            lng=loc["lng"],
            label=result["formatted_address"],
        )

    async def optimize_route(
        self,
        home: GeocodedLocation,
        stops: list[dict],
        transport_mode: str,
    ) -> RouteResult | None:
        """
        Uses Google Directions API with waypoint optimization.
        transport_mode: "driving", "walking", "bicycling", "transit"
        """
        if not stops:
            return None

        waypoints = "|".join(f"{s['lat']},{s['lng']}" for s in stops)
        origin = f"{home.lat},{home.lng}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE}/directions/json",
                params={
                    "origin": origin,
                    "destination": origin,  # circular route
                    "waypoints": f"optimize:true|{waypoints}",
                    "mode": transport_mode,
                    "key": self.key,
                },
            )
            data = resp.json()

        if data["status"] != "OK" or not data["routes"]:
            return None

        route = data["routes"][0]
        order = route.get("waypoint_order", list(range(len(stops))))

        ordered_stops = [
            {"name": f"🏠 Home", "lat": home.lat, "lng": home.lng}
        ]
        for idx in order:
            ordered_stops.append(stops[idx])
        ordered_stops.append({"name": f"🏠 Home", "lat": home.lat, "lng": home.lng})

        total_distance = sum(leg["distance"]["value"] for leg in route["legs"])
        total_duration = sum(leg["duration"]["value"] for leg in route["legs"])

        return RouteResult(
            ordered_stops=ordered_stops,
            distance_km=round(total_distance / 1000, 2),
            duration_min=round(total_duration / 60, 1),
            polyline=route["overview_polyline"]["points"],
        )
