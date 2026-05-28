"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { GroceryList } from "@/components/GroceryList";
import { RecipeParser } from "@/components/RecipeParser";
import { BasketResult } from "@/components/BasketResult";
import { MapView } from "@/components/MapView";
import { TransitSteps } from "@/components/TransitSteps";

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

  // Re-route when transport mode changes (requires a previous basket optimisation)
  useEffect(() => {
    if (!lastRouteParams.current || isRecalculating.current) return;
    isRecalculating.current = true;
    fetchRoute(lastRouteParams.current, transportMode).finally(() => {
      isRecalculating.current = false;
    });
  }, [transportMode, fetchRoute]);

  // Called by GroceryList after basket optimisation — auto-triggers route calculation
  const handleBasketReady = useCallback(
    async (data: any, routeParams: RouteParams) => {
      setBasket(data);
      lastRouteParams.current = routeParams;
      await fetchRoute(routeParams, transportMode);
    },
    [fetchRoute, transportMode],
  );

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
            onOptimize={handleBasketReady}
            transportMode={transportMode}
            onTransportModeChange={setTransportMode}
          />

          {basket && (
            <BasketResult basket={basket} transportMode={transportMode} />
          )}
        </div>

        {/* Right column: map + transit steps */}
        <div className="lg:sticky lg:top-8">
          <MapView
            route={route}
            basket={basket}
            transportMode={transportMode}
            onTransportModeChange={setTransportMode}
          />
          {transportMode === "transit" && route?.transit_steps?.length > 0 && (
            <TransitSteps steps={route.transit_steps} />
          )}
        </div>
      </div>
    </main>
  );
}
