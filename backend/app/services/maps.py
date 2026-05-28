"""
Maps service abstraction layer.
Supports Google Maps and OpenRouteService as backends.
Switch via MAPS_PROVIDER env var ("google" or "ors").
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class GeocodedLocation:
    lat: float
    lng: float
    label: str


@dataclass
class TransitStep:
    mode: str           # "WALKING" | "TRANSIT"
    instruction: str
    duration: str
    distance: str = ""
    line_name: str = ""
    vehicle_type: str = ""
    departure_stop: str = ""
    arrival_stop: str = ""
    num_stops: int = 0


@dataclass
class RouteResult:
    ordered_stops: list[dict]
    distance_km: float
    duration_min: float
    polyline: str | None = None
    transit_steps: list[TransitStep] = field(default_factory=list)


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
