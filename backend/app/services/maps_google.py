"""
Google Maps implementation of the maps provider.
"""

import re

import httpx

from app.config import settings
from app.services.maps import GeocodedLocation, MapsProvider, RouteResult, TransitStep


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


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
        if not stops:
            return None
        if transport_mode == "transit":
            return await self._transit_route(home, stops)
        return await self._driving_route(home, stops, transport_mode)

    async def _driving_route(
        self,
        home: GeocodedLocation,
        stops: list[dict],
        transport_mode: str,
    ) -> RouteResult | None:
        waypoints = "|".join(f"{s['lat']},{s['lng']}" for s in stops)
        origin = f"{home.lat},{home.lng}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.BASE}/directions/json",
                params={
                    "origin": origin,
                    "destination": origin,
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
        ordered_stops = [{"name": "🏠 Home", "lat": home.lat, "lng": home.lng}]
        for idx in order:
            ordered_stops.append(stops[idx])
        ordered_stops.append({"name": "🏠 Home", "lat": home.lat, "lng": home.lng})

        total_distance = sum(leg["distance"]["value"] for leg in route["legs"])
        total_duration = sum(leg["duration"]["value"] for leg in route["legs"])

        return RouteResult(
            ordered_stops=ordered_stops,
            distance_km=round(total_distance / 1000, 2),
            duration_min=round(total_duration / 60, 1),
            polyline=route["overview_polyline"]["points"],
        )

    async def _transit_route(
        self,
        home: GeocodedLocation,
        stops: list[dict],
    ) -> RouteResult | None:
        """Transit routing: home → stores → home with step-by-step public transport info."""
        origin = f"{home.lat},{home.lng}"
        waypoints = "|".join(f"{s['lat']},{s['lng']}" for s in stops)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.BASE}/directions/json",
                params={
                    "origin": origin,
                    "destination": origin,
                    "waypoints": waypoints,  # transit doesn't support optimize:true
                    "mode": "transit",
                    "key": self.key,
                    "language": "es",
                    "alternatives": "false",
                },
            )
            data = resp.json()

        if data["status"] != "OK" or not data["routes"]:
            return None

        route = data["routes"][0]
        transit_steps: list[TransitStep] = []

        for leg in route["legs"]:
            for step in leg["steps"]:
                mode = step.get("travel_mode", "")
                instruction = _strip_html(step.get("html_instructions", ""))
                duration = step.get("duration", {}).get("text", "")
                distance = step.get("distance", {}).get("text", "")

                if mode == "WALKING":
                    transit_steps.append(TransitStep(
                        mode="WALKING",
                        instruction=instruction,
                        duration=duration,
                        distance=distance,
                    ))
                elif mode == "TRANSIT":
                    td = step.get("transit_details", {})
                    line = td.get("line", {})
                    vehicle = line.get("vehicle", {})
                    transit_steps.append(TransitStep(
                        mode="TRANSIT",
                        instruction=instruction,
                        duration=duration,
                        line_name=line.get("short_name") or line.get("name", ""),
                        vehicle_type=vehicle.get("name", ""),
                        departure_stop=td.get("departure_stop", {}).get("name", ""),
                        arrival_stop=td.get("arrival_stop", {}).get("name", ""),
                        num_stops=td.get("num_stops", 0),
                    ))

        home_stop = {"name": "🏠 Home", "lat": home.lat, "lng": home.lng}
        ordered_stops = [home_stop] + stops + [home_stop]

        total_distance = sum(leg["distance"]["value"] for leg in route["legs"])
        total_duration = sum(leg["duration"]["value"] for leg in route["legs"])

        return RouteResult(
            ordered_stops=ordered_stops,
            distance_km=round(total_distance / 1000, 2),
            duration_min=round(total_duration / 60, 1),
            polyline=route["overview_polyline"]["points"],
            transit_steps=transit_steps,
        )
