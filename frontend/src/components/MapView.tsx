"use client";

import dynamic from "next/dynamic";

export interface RouteStop {
  name: string;
  lat: number;
  lng: number;
  address?: string;
}

export interface BasketItem {
  store_id: string;
  store_name: string;
  product_name: string;
  unit_price: number;
  quantity: number;
  line_total: number;
}

export interface MapProps {
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

const MapViewGoogle = dynamic(
  () => import("./MapViewGoogle").then((m) => ({ default: m.MapViewGoogle })),
  { ssr: false },
);

const MapViewLeaflet = dynamic(
  () => import("./MapViewLeaflet").then((m) => ({ default: m.MapViewLeaflet })),
  { ssr: false },
);

export function MapView(props: MapProps) {
  const provider = process.env.NEXT_PUBLIC_MAPS_PROVIDER ?? "leaflet";
  if (provider === "google") return <MapViewGoogle {...props} />;
  return <MapViewLeaflet {...props} />;
}
