"use client";

import { useState } from "react";
import { GroceryList } from "@/components/GroceryList";
import { RecipeParser } from "@/components/RecipeParser";
import { BasketResult } from "@/components/BasketResult";
import { MapView } from "@/components/MapView";

export default function Home() {
  const [categories, setCategories] = useState<string[]>([]);
  const [basket, setBasket] = useState<any>(null);
  const [route, setRoute] = useState<any>(null);
  const [transportMode, setTransportMode] = useState<string>("driving");

  return (
    <main className="max-w-7xl mx-auto px-4 py-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold">🧓 Tu IAbuela de Confianza</h1>
        <p className="text-gray-600 mt-1">
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
              onRouteReady={setRoute}
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
