"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { GroceryList } from "@/components/GroceryList";
import { RecipeParser } from "@/components/RecipeParser";
import { BasketResult } from "@/components/BasketResult";
import { MapView } from "@/components/MapView";

interface RouteParams {
  home_lat?: number;
  home_lng?: number;
  home_address?: string;
  store_ids: string[];
}

export default function Home() {
  const [categories, setCategories] = useState<string[]>([]);
  const [basket, setBasket] = useState<any>(null);
  const [route, setRoute] = useState<any>(null);
  const [transportMode, setTransportMode] = useState<string>("driving");
  const lastRouteParams = useRef<RouteParams | null>(null);
  const isRecalculating = useRef(false);

  const fetchRoute = useCallback(async (params: RouteParams, mode: string) => {
    try {
      const res = await fetch("/api/route/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...params, transport_mode: mode }),
      });
      if (!res.ok) return;
      const data = await res.json();
      setRoute(data);
    } catch (err) {
      console.error("Route recalculation failed:", err);
    }
  }, []);

  // Auto-recalculate route when transport mode changes
  useEffect(() => {
    if (!lastRouteParams.current || isRecalculating.current) return;
    isRecalculating.current = true;
    fetchRoute(lastRouteParams.current, transportMode).finally(() => {
      isRecalculating.current = false;
    });
  }, [transportMode, fetchRoute]);

  const handleRouteReady = useCallback((data: any, params?: RouteParams) => {
    setRoute(data);
    if (params) lastRouteParams.current = params;
  }, []);

  return (
    <main className="max-w-7xl mx-auto px-4 py-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-gray-100">
          🧓 Tu IAbuela de Confianza
        </h1>
        <p className="text-gray-400 mt-1">
          Optimiza tu compra semanal con inteligencia artificial
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left column: inputs */}
        <div className="space-y-6">
          <RecipeParser
            onIngredientsFound={(items) => {
              setCategories((prev) => [
                ...prev,
                ...items.map((i: any) => i.name),
              ]);
            }}
          />

          <GroceryList
            categories={categories}
            setCategories={setCategories}
            onOptimize={setBasket}
          />

          {basket && (
            <BasketResult
              basket={basket}
              onRouteReady={handleRouteReady}
              transportMode={transportMode}
            />
          )}
        </div>

        {/* Right column: map */}
        <div className="lg:sticky lg:top-8 h-[800px] w-[800px]">
          <MapView
            route={route}
            basket={basket}
            transportMode={transportMode}
            onTransportModeChange={setTransportMode}
          />
        </div>
      </div>
    </main>
  );
}
