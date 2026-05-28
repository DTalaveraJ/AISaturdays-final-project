"use client";

import { useEffect, useState } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from "react-leaflet";
import { decode } from "@googlemaps/polyline-codec";
import "leaflet/dist/leaflet.css";
import type { MapProps, RouteStop, BasketItem } from "./MapView";
import { EmptyState, RouteSummary, TransportToggle } from "./MapViewGoogle";

// Override Leaflet popup chrome with dark theme
const POPUP_CSS = `
  .leaflet-popup-content-wrapper, .leaflet-popup-tip {
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 !important;
  }
  .leaflet-popup-content { margin: 0 !important; }
`;

function createMarkerIcon(index: number, isHome: boolean): L.DivIcon {
  const color = isHome ? "#f59e0b" : "#10b981";
  const label = isHome ? "🏠" : `${index}`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="52" viewBox="0 0 40 52">
    <defs>
      <filter id="s" x="-20%" y="-10%" width="140%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="2" flood-opacity="0.4"/>
      </filter>
    </defs>
    <path d="M20 0C9 0 0 9 0 20c0 15 20 32 20 32s20-17 20-32C40 9 31 0 20 0z"
          fill="${color}" filter="url(#s)"/>
    <circle cx="20" cy="18" r="12" fill="white" opacity="0.9"/>
    <text x="20" y="23" text-anchor="middle" font-size="${isHome ? "14" : "12"}"
          font-weight="bold" fill="${color}">${label}</text>
  </svg>`;
  return L.divIcon({
    html: svg,
    className: "",
    iconSize: [40, 52],
    iconAnchor: [20, 52],
    popupAnchor: [0, -56],
  });
}

function buildPopupHtml(stop: RouteStop, items: BasketItem[], isHome: boolean): string {
  if (isHome) {
    return `<div style="font-family:system-ui,sans-serif;padding:8px;min-width:160px;background:#1a3646;border-radius:8px;">
      <div style="font-weight:600;font-size:14px;margin-bottom:4px;color:#f3f4f6;">🏠 Tu casa</div>
      <div style="color:#8ec3b9;font-size:12px;">Punto de inicio y fin</div>
    </div>`;
  }
  const itemsHtml = items.length > 0
    ? items.map((item) => `
        <div style="display:flex;justify-content:space-between;gap:12px;padding:4px 0;border-bottom:1px solid #304a7d;">
          <span style="font-size:12px;color:#d1d5db;">${item.product_name}</span>
          <span style="font-size:12px;color:#8ec3b9;white-space:nowrap;">${item.quantity}x ${item.unit_price.toFixed(2)}€</span>
        </div>`).join("")
    : `<div style="color:#6b7280;font-size:12px;">Sin productos asignados</div>`;
  const total = items.reduce((s, i) => s + i.line_total, 0);
  return `<div style="font-family:system-ui,sans-serif;padding:8px;min-width:220px;max-width:300px;background:#1a3646;border-radius:8px;">
    <div style="font-weight:600;font-size:14px;color:#10b981;margin-bottom:2px;">🛒 ${stop.name}</div>
    ${stop.address ? `<div style="color:#6f9ba5;font-size:11px;margin-bottom:8px;">${stop.address}</div>` : ""}
    <div style="font-size:11px;font-weight:600;color:#8ec3b9;margin-bottom:4px;text-transform:uppercase;">Productos a comprar:</div>
    <div style="max-height:150px;overflow-y:auto;">${itemsHtml}</div>
    ${items.length > 0 ? `
      <div style="margin-top:8px;padding-top:6px;border-top:2px solid #2c6675;display:flex;justify-content:space-between;font-weight:600;font-size:13px;">
        <span style="color:#d1d5db;">Subtotal</span>
        <span style="color:#10b981;">${total.toFixed(2)}€</span>
      </div>` : ""}
  </div>`;
}

function MapResizer({ routeKey }: { routeKey: string }) {
  const map = useMap();
  useEffect(() => {
    const t = setTimeout(() => map.invalidateSize(), 200);
    return () => clearTimeout(t);
  }, [map, routeKey]);
  return null;
}

// Must be defined outside the main component so React doesn't recreate the type on every render
function FitBounds({ stops }: { stops: RouteStop[] }) {
  const map = useMap();
  useEffect(() => {
    const unique = stops.slice(0, -1);
    if (unique.length > 0) {
      const bounds = L.latLngBounds(unique.map((s) => [s.lat, s.lng] as [number, number]));
      map.fitBounds(bounds, { padding: [60, 60] });
    }
  }, [stops, map]);
  return null;
}

export function MapViewLeaflet({ route, basket, transportMode, onTransportModeChange }: MapProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // Group basket items by store name
  const itemsByStore: Record<string, BasketItem[]> = {};
  if (basket?.items) {
    for (const item of basket.items) {
      if (!itemsByStore[item.store_name]) itemsByStore[item.store_name] = [];
      itemsByStore[item.store_name].push(item);
    }
  }

  const polylinePath: [number, number][] | null = route?.polyline
    ? (decode(route.polyline) as [number, number][])
    : null;

  const fallbackPath: [number, number][] = route?.ordered_stops
    ? route.ordered_stops.map((s) => [s.lat, s.lng])
    : [];

  // Changes when route updates so MapResizer re-fires invalidateSize after FitBounds repositions
  const routeKey = route
    ? `${route.ordered_stops?.length ?? 0}-${route.distance_km ?? 0}`
    : "empty";

  if (!mounted) {
    return <div style={{ height: "700px" }} className="bg-gray-900 rounded-lg border border-gray-700" />;
  }

  return (
    <div className="rounded-lg overflow-hidden shadow-xl relative border border-gray-700">
      <style dangerouslySetInnerHTML={{ __html: POPUP_CSS }} />

      <MapContainer
        center={[40.33, -3.76]}
        zoom={13}
        style={{ width: "100%", height: "700px" }}
        zoomControl
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          maxZoom={20}
        />

        <MapResizer routeKey={routeKey} />
        {route?.ordered_stops && <FitBounds stops={route.ordered_stops} />}

        {route?.ordered_stops?.slice(0, -1).map((stop, idx) => {
          const isHome = idx === 0;
          const storeItems = itemsByStore[stop.name] || [];
          return (
            <Marker
              key={idx}
              position={[stop.lat, stop.lng]}
              icon={createMarkerIcon(idx, isHome)}
              zIndexOffset={isHome ? 100 : 50 - idx}
              eventHandlers={{
                mouseover: (e: { target: { openPopup: () => void } }) => e.target.openPopup(),
                mouseout: (e: { target: { closePopup: () => void } }) => e.target.closePopup(),
              }}
            >
              <Popup>
                <div dangerouslySetInnerHTML={{ __html: buildPopupHtml(stop, storeItems, isHome) }} />
              </Popup>
            </Marker>
          );
        })}

        {polylinePath ? (
          <>
            <Polyline positions={polylinePath} pathOptions={{ color: "#10b981", weight: 8, opacity: 0.3 }} />
            <Polyline positions={polylinePath} pathOptions={{ color: "#10b981", weight: 4, opacity: 0.9 }} />
          </>
        ) : fallbackPath.length > 1 ? (
          <>
            <Polyline positions={fallbackPath} pathOptions={{ color: "#10b981", weight: 8, opacity: 0.3 }} />
            <Polyline positions={fallbackPath} pathOptions={{ color: "#10b981", weight: 3, dashArray: "8 8", opacity: 0.9 }} />
          </>
        ) : null}
      </MapContainer>

      <TransportToggle transportMode={transportMode} onTransportModeChange={onTransportModeChange} />
      <RouteSummary route={route} basket={basket} transportMode={transportMode} />
      {!route && <EmptyState />}
    </div>
  );
}
