"use client";

import { useState } from "react";

interface Props {
  categories: string[];
  setCategories: (cats: string[]) => void;
  onOptimize: (basket: any) => void;
}

export function GroceryList({ categories, setCategories, onOptimize }: Props) {
  const [input, setInput] = useState("");
  const [budget, setBudget] = useState(35);
  const [nPeople, setNPeople] = useState(2);
  const [maxShops, setMaxShops] = useState(3);
  const [loading, setLoading] = useState(false);

  const addItem = () => {
    if (input.trim()) {
      setCategories([...categories, input.trim().toLowerCase()]);
      setInput("");
    }
  };

  const removeItem = (idx: number) => {
    setCategories(categories.filter((_, i) => i !== idx));
  };

  const [smartMatch, setSmartMatch] = useState(false);

  const handleOptimize = async () => {
    if (categories.length === 0) return;
    setLoading(true);
    try {
      const res = await fetch("/api/basket/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          categories,
          budget,
          n_people: nPeople,
          max_shops: maxShops,
          smart_match: smartMatch,
        }),
      });
      if (!res.ok) {
        const errText = await res.text();
        console.error("Basket error:", res.status, errText);
        alert(`Error al optimizar: ${errText}`);
        return;
      }
      const data = await res.json();
      onOptimize(data);
    } catch (err) {
      console.error("Basket optimization failed:", err);
      alert("Error de conexión al optimizar la cesta");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#1a3646] rounded-lg shadow-lg border border-[#2c6675] p-4">
      <h2 className="font-semibold text-lg mb-2 text-gray-100">
        🛒 Lista de la compra
      </h2>

      {/* Add item */}
      <div className="flex gap-2 mb-3">
        <input
          type="text"
          className="flex-1 bg-[#0e1626] border border-[#304a7d] rounded-md px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 focus:border-[#2c6675] focus:outline-none"
          placeholder="Añadir producto (ej: leche, pan, pollo...)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addItem()}
        />
        <button
          onClick={addItem}
          className="px-3 py-1.5 bg-green-600 text-white rounded-md text-sm hover:bg-green-700"
        >
          +
        </button>
      </div>

      {/* Item list */}
      {categories.length > 0 && (
        <ul className="space-y-1 mb-4">
          {categories.map((cat, idx) => (
            <li
              key={idx}
              className="flex justify-between items-center text-sm bg-[#0e1626] border border-[#304a7d] px-3 py-1.5 rounded text-gray-200"
            >
              <span>{cat}</span>
              <button
                onClick={() => removeItem(idx)}
                className="text-red-400 hover:text-red-300"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Settings */}
      <div className="grid grid-cols-3 gap-3 mb-4 text-sm">
        <label className="flex flex-col">
          <span className="text-gray-400">Presupuesto €</span>
          <input
            type="number"
            value={budget}
            onChange={(e) => setBudget(+e.target.value)}
            className="bg-[#0e1626] border border-[#304a7d] rounded px-2 py-1 mt-1 text-gray-200 focus:border-[#2c6675] focus:outline-none"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-gray-400">Personas</span>
          <input
            type="number"
            value={nPeople}
            onChange={(e) => setNPeople(+e.target.value)}
            className="bg-[#0e1626] border border-[#304a7d] rounded px-2 py-1 mt-1 text-gray-200 focus:border-[#2c6675] focus:outline-none"
            min={1}
          />
        </label>
        <label className="flex flex-col">
          <span className="text-gray-400">Máx. tiendas</span>
          <input
            type="number"
            value={maxShops}
            onChange={(e) => setMaxShops(+e.target.value)}
            className="bg-[#0e1626] border border-[#304a7d] rounded px-2 py-1 mt-1 text-gray-200 focus:border-[#2c6675] focus:outline-none"
            min={1}
          />
        </label>
      </div>

      {/* Smart match toggle */}
      <label className="flex items-center gap-2 mb-4 cursor-pointer">
        <input
          type="checkbox"
          checked={smartMatch}
          onChange={(e) => setSmartMatch(e.target.checked)}
          className="rounded border-[#304a7d] bg-[#0e1626]"
        />
        <span className="text-sm text-gray-400">
          🧠 Búsqueda inteligente (usa IA para filtrar productos relevantes)
        </span>
      </label>

      <button
        onClick={handleOptimize}
        disabled={loading || categories.length === 0}
        className="w-full py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700
                   disabled:opacity-50 font-medium"
      >
        {loading ? "Optimizando..." : "🔍 Optimizar cesta"}
      </button>
    </div>
  );
}
