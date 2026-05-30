"use client";

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

interface RouteStop {
  name: string;
  address?: string;
}

interface Props {
  basket: {
    items: BasketItem[];
    total_cost: number;
    stores_used: string[];
    suggestions?: Suggestion[];
    estimated_travel_min?: number;
  };
  transportMode: string;
  route?: { ordered_stops: RouteStop[] } | null;
}

export function BasketResult({ basket, transportMode, route }: Props) {
  // Group items by store
  const byStore: Record<string, BasketItem[]> = {};

  // Address lookup: store name → address (from route stops)
  const storeAddress: Record<string, string> = {};
  if (route?.ordered_stops) {
    for (const stop of route.ordered_stops) {
      if (stop.address) storeAddress[stop.name] = stop.address;
    }
  }
  for (const item of basket.items) {
    if (!byStore[item.store_name]) byStore[item.store_name] = [];
    byStore[item.store_name].push(item);
  }

  const transportLabel: Record<string, string> = {
    driving: "en coche",
    walking: "a pie",
    bicycling: "en bici",
    transit: "en transporte público",
  };

  return (
    <div className="bg-[#1a3646] rounded-lg shadow-lg border border-[#2c6675] p-4">
      <h2 className="font-semibold text-lg mb-2 text-gray-100">
        ✅ Cesta optimizada
      </h2>

      {/* Estimated travel time */}
      {basket.estimated_travel_min != null && (
        <div className="mb-3 flex items-center gap-2 text-sm bg-[#0e1626] border border-[#304a7d] rounded-md px-3 py-2">
          <span className="text-[#8ec3b9]">⏱️</span>
          <span className="text-gray-300">
            Tiempo estimado de desplazamiento:{" "}
            <span className="font-semibold text-[#8ec3b9]">
              ~{basket.estimated_travel_min} min
            </span>{" "}
            <span className="text-gray-500">
              {transportLabel[transportMode] ?? ""}
            </span>
          </span>
        </div>
      )}

      {/* Suggestions / substitutions */}
      {basket.suggestions && basket.suggestions.length > 0 && (
        <div className="mb-4 space-y-2">
          {basket.suggestions.map((sug, idx) => (
            <div
              key={idx}
              className="bg-amber-900/30 border border-amber-700/50 rounded-md p-3"
            >
              <div className="flex items-start gap-2">
                <span className="text-amber-400 text-lg">💡</span>
                <div className="flex-1">
                  <p className="text-sm font-medium text-amber-300">
                    No se encontró: &quot;{sug.category}&quot;
                  </p>
                  {sug.product_name && (
                    <p className="text-sm text-amber-400 mt-0.5">
                      Sugerencia:{" "}
                      <span className="font-medium">{sug.product_name}</span>
                    </p>
                  )}
                  <p className="text-xs text-amber-500 mt-0.5">{sug.reason}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Items grouped by store */}
      {Object.entries(byStore).map(([store, items]) => (
        <div key={store} className="mb-3">
          <h3 className="font-medium text-sm text-[#8ec3b9]">
            📍 {store}
            {storeAddress[store] && (
              <span className="font-normal text-gray-500 ml-1">
                ({storeAddress[store]})
              </span>
            )}
          </h3>
          <ul className="ml-4 text-sm space-y-0.5">
            {items.map((item, idx) => (
              <li key={idx} className="flex justify-between text-gray-300">
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

      <div className="border-t border-[#304a7d] pt-2 mt-2 flex justify-between font-semibold text-gray-100">
        <span>Total</span>
        <span className="text-green-400">{basket.total_cost.toFixed(2)}€</span>
      </div>
    </div>
  );
}
