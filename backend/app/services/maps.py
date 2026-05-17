"""
Maps service abstraction layer.
Supports Google Maps and OpenRouteService as backends.
Switch via MAPS_PROVIDER env var ("google" or "ors").
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.config import settings


@dataclass
class GeocodedLocation:
    lat: float
    lng: float
    label: str


@dataclass
class RouteResult:
    ordered_stops: list[dict]
    distance_km: float
    duration_min: float
    polyline: str | None = None  # encoded polyline for map rendering


class MapsProvider(ABC):
    @abstractmethod
    async def geocode(self, address: str) -> GeocodedLocation | None:
        ...

    @abstractmethod
    async def optimize_route(
        self,
        home: GeocodedLocation,
        stops: list[dict],
        transport_mode: str,
    ) -> RouteResult | None:
        ...
