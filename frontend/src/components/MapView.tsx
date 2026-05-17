"use client";

import { useEffect, useRef, useState } from "react";

interface RouteStop {
  name: string;
  lat: number;
  lng: number;
  address?: string;
}

interface Props {
  route: {
    ordered_stops: RouteStop[];
    distance_km: number;
    duration_min: number;
    polyline?: string;
  } | null;
  basket: any;
}

export function MapView({ route, basket }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<google.maps.Map | null>(null);
  const [loaded, setLoaded] = useState(false);

  // Load Google Maps script
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.google?.maps) {
      setLoaded(true);
      return;
    }

    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    if (!apiKey) return;

    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=geometry`;
    script.async = true;
    script.onload = () => setLoaded(true);
    document.head.appendChild(script);
  }, []);

  // Initialize map
  useEffect(() => {
    if (!loaded || !mapRef.current || map) return;

    const newMap = new google.maps.Map(mapRef.current, {
      center: { lat: 40.33, lng: -3.76 }, // Default: Leganés area
      zoom: 13,
      mapId: "iabuela-map",
    });
    setMap(newMap);
  }, [loaded, map]);

  // Draw route when available
  useEffect(() => {
    if (!map || !route?.ordered_stops) return;

    // Clear previous markers/polylines
    // (In production, store refs and clear them)

    const bounds = new google.maps.LatLngBounds();

    // Add markers
    route.ordered_stops.forEach((stop, idx) => {
      const position = { lat: stop.lat, lng: stop.lng };
      bounds.extend(position);

      new google.maps.Marker({
        position,
        map,
        label:
          idx === 0 || idx === route.ordered_stops.length - 1 ? "🏠" : `${idx}`,
        title: stop.name,
      });
    });

    // Draw polyline if available (from Google Directions)
    if (route.polyline) {
      const path = google.maps.geometry.encoding.decodePath(route.polyline);
      new google.maps.Polyline({
        path,
        map,
        strokeColor: "#2563eb",
        strokeWeight: 4,
        strokeOpacity: 0.8,
      });
    } else {
      // Fallback: straight lines between stops
      const path = route.ordered_stops.map((s) => ({ lat: s.lat, lng: s.lng }));
      new google.maps.Polyline({
        path,
        map,
        strokeColor: "#2563eb",
        strokeWeight: 3,
        strokeOpacity: 0.6,
        geodesic: true,
      });
    }

    map.fitBounds(bounds, 50);
  }, [map, route]);

  if (!process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY) {
    return (
      <div className="h-full bg-gray-100 rounded-lg flex items-center justify-center text-gray-500">
        <p className="text-center text-sm">
          Set NEXT_PUBLIC_GOOGLE_MAPS_API_KEY
          <br />
          to enable the map
        </p>
      </div>
    );
  }

  return (
    <div className="h-full rounded-lg overflow-hidden shadow relative">
      <div ref={mapRef} className="w-full h-full" />
      {route && (
        <div className="absolute bottom-4 left-4 bg-white/90 backdrop-blur rounded-lg px-4 py-2 text-sm shadow">
          <span className="font-medium">{route.distance_km} km</span>
          <span className="mx-2 text-gray-400">·</span>
          <span className="font-medium">{route.duration_min} min</span>
        </div>
      )}
    </div>
  );
}
