"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface RouteStop {
  name: string;
  lat: number;
  lng: number;
  address?: string;
}

interface BasketItem {
  store_id: string;
  store_name: string;
  product_name: string;
  unit_price: number;
  quantity: number;
  line_total: number;
}

interface Props {
  route: {
    ordered_stops: RouteStop[];
    distance_km: number;
    duration_min: number;
    polyline?: string;
  } | null;
  basket: {
    items: BasketItem[];
    total_cost: number;
    stores_used: string[];
  } | null;
  transportMode: string;
  onTransportModeChange: (mode: string) => void;
}

// Dark-themed map style for a sleek look
const MAP_STYLES: google.maps.MapTypeStyle[] = [
  { elementType: "geometry", stylers: [{ color: "#1d2c4d" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#8ec3b9" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#1a3646" }] },
  {
    featureType: "administrative.country",
    elementType: "geometry.stroke",
    stylers: [{ color: "#4b6878" }],
  },
  {
    featureType: "administrative.province",
    elementType: "geometry.stroke",
    stylers: [{ color: "#4b6878" }],
  },
  {
    featureType: "landscape",
    elementType: "labels",
    stylers: [{ visibility: "off" }],
  },
  {
    featureType: "poi",
    elementType: "geometry",
    stylers: [{ color: "#283d6a" }],
  },
  {
    featureType: "poi",
    elementType: "labels.text.fill",
    stylers: [{ color: "#6f9ba5" }],
  },
  {
    featureType: "poi.park",
    elementType: "geometry.fill",
    stylers: [{ color: "#023e58" }],
  },
  {
    featureType: "road",
    elementType: "geometry",
    stylers: [{ color: "#304a7d" }],
  },
  {
    featureType: "road",
    elementType: "labels.text.fill",
    stylers: [{ color: "#98a5be" }],
  },
  {
    featureType: "road.highway",
    elementType: "geometry",
    stylers: [{ color: "#2c6675" }],
  },
  {
    featureType: "road.highway",
    elementType: "geometry.stroke",
    stylers: [{ color: "#255763" }],
  },
  {
    featureType: "transit",
    elementType: "labels.text.fill",
    stylers: [{ color: "#98a5be" }],
  },
  {
    featureType: "water",
    elementType: "geometry.fill",
    stylers: [{ color: "#0e1626" }],
  },
  {
    featureType: "water",
    elementType: "labels.text.fill",
    stylers: [{ color: "#4e6d70" }],
  },
];

// Custom marker SVG for stores
function createStoreMarkerIcon(
  index: number,
  isHome: boolean,
): google.maps.Icon {
  const color = isHome ? "#f59e0b" : "#10b981";
  const label = isHome ? "🏠" : `${index}`;
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="40" height="52" viewBox="0 0 40 52">
      <defs>
        <filter id="shadow" x="-20%" y="-10%" width="140%" height="140%">
          <feDropShadow dx="0" dy="2" stdDeviation="2" flood-opacity="0.4"/>
        </filter>
      </defs>
      <path d="M20 0C9 0 0 9 0 20c0 15 20 32 20 32s20-17 20-32C40 9 31 0 20 0z"
            fill="${color}" filter="url(#shadow)"/>
      <circle cx="20" cy="18" r="12" fill="white" opacity="0.9"/>
      <text x="20" y="23" text-anchor="middle" font-size="${isHome ? "14" : "12"}"
            font-weight="bold" fill="${color}">${label}</text>
    </svg>`;
  return {
    url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
    scaledSize: new google.maps.Size(40, 52),
    anchor: new google.maps.Point(20, 52),
  };
}

// Build HTML content for the InfoWindow popup
function buildInfoWindowContent(
  stop: RouteStop,
  items: BasketItem[],
  isHome: boolean,
): string {
  if (isHome) {
    return `
      <div style="font-family: system-ui, sans-serif; padding: 8px; min-width: 160px; background: #1a3646; border-radius: 8px;">
        <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px; color: #f3f4f6;">🏠 Tu casa</div>
        <div style="color: #8ec3b9; font-size: 12px;">Punto de inicio y fin</div>
      </div>`;
  }

  const itemsHtml =
    items.length > 0
      ? items
          .map(
            (item) => `
        <div style="display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; border-bottom: 1px solid #304a7d;">
          <span style="font-size: 12px; color: #d1d5db;">${item.product_name}</span>
          <span style="font-size: 12px; color: #8ec3b9; white-space: nowrap;">${item.quantity}x ${item.unit_price.toFixed(2)}€</span>
        </div>`,
          )
          .join("")
      : `<div style="color: #6b7280; font-size: 12px;">Sin productos asignados</div>`;

  const total = items.reduce((sum, i) => sum + i.line_total, 0);

  return `
    <div style="font-family: system-ui, sans-serif; padding: 8px; min-width: 220px; max-width: 300px; background: #1a3646; border-radius: 8px;">
      <div style="font-weight: 600; font-size: 14px; color: #10b981; margin-bottom: 2px;">
        🛒 ${stop.name}
      </div>
      ${stop.address ? `<div style="color: #6f9ba5; font-size: 11px; margin-bottom: 8px;">${stop.address}</div>` : ""}
      <div style="font-size: 11px; font-weight: 600; color: #8ec3b9; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;">
        Productos a comprar:
      </div>
      <div style="max-height: 150px; overflow-y: auto;">
        ${itemsHtml}
      </div>
      ${
        items.length > 0
          ? `
        <div style="margin-top: 8px; padding-top: 6px; border-top: 2px solid #2c6675; display: flex; justify-content: space-between; font-weight: 600; font-size: 13px;">
          <span style="color: #d1d5db;">Subtotal</span>
          <span style="color: #10b981;">${total.toFixed(2)}€</span>
        </div>`
          : ""
      }
    </div>`;
}

export function MapView({
  route,
  basket,
  transportMode,
  onTransportModeChange,
}: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<google.maps.Map | null>(null);
  const markersRef = useRef<google.maps.Marker[]>([]);
  const polylinesRef = useRef<google.maps.Polyline[]>([]);
  const infoWindowRef = useRef<google.maps.InfoWindow | null>(null);
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
    if (!loaded || !mapRef.current || mapInstance.current) return;

    mapInstance.current = new google.maps.Map(mapRef.current, {
      center: { lat: 40.33, lng: -3.76 },
      zoom: 13,
      styles: MAP_STYLES,
      disableDefaultUI: false,
      zoomControl: true,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: true,
    });

    infoWindowRef.current = new google.maps.InfoWindow();
  }, [loaded]);

  // Clear previous overlays
  const clearOverlays = useCallback(() => {
    markersRef.current.forEach((m) => m.setMap(null));
    markersRef.current = [];
    polylinesRef.current.forEach((p) => p.setMap(null));
    polylinesRef.current = [];
    infoWindowRef.current?.close();
  }, []);

  // Draw route when available
  useEffect(() => {
    const map = mapInstance.current;
    if (!map || !route?.ordered_stops) return;

    clearOverlays();

    // Group basket items by store name for InfoWindow content
    const itemsByStore: Record<string, BasketItem[]> = {};
    if (basket?.items) {
      for (const item of basket.items) {
        if (!itemsByStore[item.store_name]) itemsByStore[item.store_name] = [];
        itemsByStore[item.store_name].push(item);
      }
    }

    const bounds = new google.maps.LatLngBounds();
    const infoWindow = infoWindowRef.current!;

    // Add markers with hover InfoWindows
    route.ordered_stops.forEach((stop, idx) => {
      const isHome = idx === 0 || idx === route.ordered_stops.length - 1;
      // Skip duplicate home marker at end
      if (idx === route.ordered_stops.length - 1) return;

      const position = { lat: stop.lat, lng: stop.lng };
      bounds.extend(position);

      const marker = new google.maps.Marker({
        position,
        map,
        icon: createStoreMarkerIcon(idx, isHome),
        title: stop.name,
        animation: google.maps.Animation.DROP,
        zIndex: isHome ? 100 : 50 - idx,
      });

      // Get items for this store
      const storeItems = itemsByStore[stop.name] || [];
      const content = buildInfoWindowContent(stop, storeItems, isHome);

      // Show InfoWindow on hover
      marker.addListener("mouseover", () => {
        infoWindow.setContent(content);
        infoWindow.open(map, marker);
      });

      marker.addListener("mouseout", () => {
        infoWindow.close();
      });

      // Keep open on click
      marker.addListener("click", () => {
        infoWindow.setContent(content);
        infoWindow.open(map, marker);
      });

      markersRef.current.push(marker);
    });

    // Draw route polyline
    if (route.polyline) {
      const path = google.maps.geometry.encoding.decodePath(route.polyline);

      // Glow effect (wider, semi-transparent line behind)
      const glow = new google.maps.Polyline({
        path,
        map,
        strokeColor: "#10b981",
        strokeWeight: 8,
        strokeOpacity: 0.3,
      });
      polylinesRef.current.push(glow);

      // Main route line
      const line = new google.maps.Polyline({
        path,
        map,
        strokeColor: "#10b981",
        strokeWeight: 4,
        strokeOpacity: 0.9,
      });
      polylinesRef.current.push(line);
    } else {
      // Fallback: animated dashed line between stops
      const path = route.ordered_stops.map((s) => ({ lat: s.lat, lng: s.lng }));

      const line = new google.maps.Polyline({
        path,
        map,
        strokeColor: "#10b981",
        strokeWeight: 3,
        strokeOpacity: 0,
        geodesic: true,
        icons: [
          {
            icon: {
              path: "M 0,-1 0,1",
              strokeOpacity: 0.8,
              strokeColor: "#10b981",
              scale: 3,
            },
            offset: "0",
            repeat: "16px",
          },
        ],
      });
      polylinesRef.current.push(line);
    }

    map.fitBounds(bounds, 60);
  }, [route, clearOverlays, basket]);

  if (!process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY) {
    return (
      <div className="h-full bg-gray-900 rounded-lg flex items-center justify-center text-gray-400 border border-gray-700">
        <div className="text-center">
          <div className="text-4xl mb-3">🗺️</div>
          <p className="text-sm">
            Configura{" "}
            <code className="bg-gray-800 px-1.5 py-0.5 rounded text-xs">
              NEXT_PUBLIC_GOOGLE_MAPS_API_KEY
            </code>
            <br />
            para activar el mapa interactivo
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full rounded-lg overflow-hidden shadow-xl relative border border-gray-700">
      <div ref={mapRef} className="w-full h-full" />

      {/* Transport mode toggle */}
      <div
        className="absolute top-4 left-4 bg-gray-900/90 backdrop-blur-sm rounded-lg
                      shadow-lg border border-gray-700 flex overflow-hidden"
      >
        {[
          { mode: "driving", icon: "🚗", label: "Coche" },
          { mode: "walking", icon: "🚶", label: "A pie" },
          { mode: "transit", icon: "🚌", label: "Transporte" },
          { mode: "bicycling", icon: "🚴", label: "Bici" },
        ].map(({ mode, icon, label }) => (
          <button
            key={mode}
            onClick={() => onTransportModeChange(mode)}
            className={`px-3 py-2 text-xs font-medium transition-colors flex flex-col items-center gap-0.5
              ${
                transportMode === mode
                  ? "bg-green-600 text-white"
                  : "text-gray-300 hover:bg-gray-700/50"
              }`}
            title={label}
          >
            <span className="text-base">{icon}</span>
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* Route summary overlay */}
      {route && (
        <div
          className="absolute bottom-4 left-4 right-4 bg-gray-900/90 backdrop-blur-sm
                        rounded-xl px-5 py-3 shadow-lg border border-gray-700
                        flex items-center justify-between"
        >
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <span className="text-green-400 text-lg">📍</span>
              <span className="text-white font-semibold">
                {route.ordered_stops.length - 2} tiendas
              </span>
            </div>
            <div className="w-px h-5 bg-gray-600" />
            <div className="flex items-center gap-1.5">
              <span className="text-blue-400 text-sm">
                {transportMode === "driving"
                  ? "🚗"
                  : transportMode === "walking"
                    ? "🚶"
                    : transportMode === "bicycling"
                      ? "🚴"
                      : "🚌"}
              </span>
              <span className="text-gray-200 font-medium">
                {route.distance_km} km
              </span>
            </div>
            <div className="w-px h-5 bg-gray-600" />
            <div className="flex items-center gap-1.5">
              <span className="text-purple-400 text-sm">⏱️</span>
              <span className="text-gray-200 font-medium">
                {route.duration_min} min
              </span>
            </div>
          </div>
          {basket && (
            <div className="text-green-400 font-bold text-lg">
              {basket.total_cost.toFixed(2)}€
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!route && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center text-gray-400 bg-gray-900/60 backdrop-blur-sm rounded-xl px-6 py-4">
            <div className="text-3xl mb-2">🛒</div>
            <p className="text-sm">
              Optimiza tu cesta y calcula la ruta
              <br />
              para ver el mapa interactivo
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
