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

interface Suggestion {
  category: string;
  product_id: string;
  product_name: string;
  reason: string;
}

interface Props {
  basket: {
    items: BasketItem[];
    total_cost: number;
    stores_used: string[];
    suggestions?: Suggestion[];
  };
  onRouteReady: (route: any) => void;
  transportMode: string;
}

export function BasketResult({ basket, onRouteReady, transportMode }: Props) {
  const [loading, setLoading] = useState(false);
  const [locationMode, setLocationMode] = useState<"gps" | "address">("gps");
  const [address, setAddress] = useState("");

  // Group items by store
  const byStore: Record<string, BasketItem[]> = {};
  for (const item of basket.items) {
    if (!byStore[item.store_name]) byStore[item.store_name] = [];
    byStore[item.store_name].push(item);
  }

  const handleRoute = async () => {
    setLoading(true);
    try {
      let body: any = {
        store_ids: basket.stores_used,
        transport_mode: transportMode,
      };

      if (locationMode === "gps") {
        const pos = await new Promise<GeolocationPosition>((resolve, reject) =>
          navigator.geolocation.getCurrentPosition(resolve, reject),
        );
        body.home_lat = pos.coords.latitude;
        body.home_lng = pos.coords.longitude;
      } else {
        if (!address.trim()) {
          alert("Introduce una dirección de inicio");
          setLoading(false);
          return;
        }
        body.home_address = address.trim();
      }

      const res = await fetch("/api/route/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const errText = await res.text();
        console.error("Route error:", res.status, errText);
        alert(`Error al calcular ruta: ${errText}`);
        return;
      }
      const data = await res.json();
      onRouteReady(data);
    } catch (err) {
      console.error("Route optimization failed:", err);
      alert("Error al calcular la ruta. Verifica tu ubicación o dirección.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h2 className="font-semibold text-lg mb-2">✅ Cesta optimizada</h2>

      {/* Suggestions / substitutions */}
      {basket.suggestions && basket.suggestions.length > 0 && (
        <div className="mb-4 space-y-2">
          {basket.suggestions.map((sug, idx) => (
            <div
              key={idx}
              className="bg-amber-50 border border-amber-200 rounded-md p-3"
            >
              <div className="flex items-start gap-2">
                <span className="text-amber-500 text-lg">💡</span>
                <div className="flex-1">
                  <p className="text-sm font-medium text-amber-800">
                    No se encontró: &quot;{sug.category}&quot;
                  </p>
                  {sug.product_name && (
                    <p className="text-sm text-amber-700 mt-0.5">
                      Sugerencia:{" "}
                      <span className="font-medium">{sug.product_name}</span>
                    </p>
                  )}
                  <p className="text-xs text-amber-600 mt-0.5">{sug.reason}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Items grouped by store */}
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

      {/* Location selector */}
      <div className="mt-4 border-t pt-4">
        <p className="text-sm font-medium text-gray-700 mb-2">
          📍 Punto de inicio
        </p>
        <div className="flex gap-2 mb-2">
          <button
            onClick={() => setLocationMode("gps")}
            className={`flex-1 py-1.5 text-sm rounded-md border transition-colors ${
              locationMode === "gps"
                ? "bg-blue-50 border-blue-300 text-blue-700 font-medium"
                : "border-gray-200 text-gray-500 hover:bg-gray-50"
            }`}
          >
            📡 Mi ubicación
          </button>
          <button
            onClick={() => setLocationMode("address")}
            className={`flex-1 py-1.5 text-sm rounded-md border transition-colors ${
              locationMode === "address"
                ? "bg-blue-50 border-blue-300 text-blue-700 font-medium"
                : "border-gray-200 text-gray-500 hover:bg-gray-50"
            }`}
          >
            ✏️ Escribir dirección
          </button>
        </div>

        {locationMode === "address" && (
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Ej: Calle Gran Vía 1, Madrid"
            className="w-full border rounded-md px-3 py-2 text-sm mb-2"
            onKeyDown={(e) => e.key === "Enter" && handleRoute()}
          />
        )}
      </div>

      <button
        onClick={handleRoute}
        disabled={loading}
        className="w-full mt-3 py-2 bg-green-600 text-white rounded-md
                   hover:bg-green-700 disabled:opacity-50 font-medium"
      >
        {loading ? "Calculando ruta..." : "🗺️ Calcular ruta óptima"}
      </button>
    </div>
  );
}
