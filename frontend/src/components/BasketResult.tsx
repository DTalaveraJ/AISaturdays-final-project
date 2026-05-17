"use client";

import { useState } from "react";

interface BasketItem {
  store_id: string;
  store_name: string;
  product_name: string;
  unit_price: number;
  quantity: number;
  line_total: number;
}

interface Props {
  basket: {
    items: BasketItem[];
    total_cost: number;
    stores_used: string[];
  };
  onRouteReady: (route: any) => void;
  transportMode: string;
}

export function BasketResult({ basket, onRouteReady, transportMode }: Props) {
  const [loading, setLoading] = useState(false);

  // Group items by store
  const byStore: Record<string, BasketItem[]> = {};
  for (const item of basket.items) {
    if (!byStore[item.store_name]) byStore[item.store_name] = [];
    byStore[item.store_name].push(item);
  }

  const handleRoute = async () => {
    setLoading(true);
    try {
      // Use browser geolocation
      const pos = await new Promise<GeolocationPosition>((resolve, reject) =>
        navigator.geolocation.getCurrentPosition(resolve, reject),
      );

      const res = await fetch("/api/route/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          home_lat: pos.coords.latitude,
          home_lng: pos.coords.longitude,
          store_ids: basket.stores_used,
          transport_mode: transportMode,
        }),
      });
      const data = await res.json();
      onRouteReady(data);
    } catch (err) {
      console.error("Route optimization failed:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h2 className="font-semibold text-lg mb-2">✅ Cesta optimizada</h2>

      {Object.entries(byStore).map(([store, items]) => (
        <div key={store} className="mb-3">
          <h3 className="font-medium text-sm text-blue-700">📍 {store}</h3>
          <ul className="ml-4 text-sm space-y-0.5">
            {items.map((item, idx) => (
              <li key={idx} className="flex justify-between">
                <span>{item.product_name}</span>
                <span className="text-gray-500">
                  {item.quantity}x {item.unit_price.toFixed(2)}€ ={" "}
                  {item.line_total.toFixed(2)}€
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}

      <div className="border-t pt-2 mt-2 flex justify-between font-semibold">
        <span>Total</span>
        <span>{basket.total_cost.toFixed(2)}€</span>
      </div>

      <button
        onClick={handleRoute}
        disabled={loading}
        className="w-full mt-4 py-2 bg-green-600 text-white rounded-md
                   hover:bg-green-700 disabled:opacity-50 font-medium"
      >
        {loading ? "Calculando ruta..." : "🗺️ Calcular ruta óptima"}
      </button>
    </div>
  );
}
