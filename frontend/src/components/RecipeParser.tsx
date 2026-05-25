"use client";

import { useState } from "react";

interface Props {
  onIngredientsFound: (ingredients: any[]) => void;
}

export function RecipeParser({ onIngredientsFound }: Props) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);

  const handleParse = async () => {
    if (!text.trim()) return;
    setLoading(true);
    try {
      const res = await fetch("/api/recipe/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        const errText = await res.text();
        console.error("Recipe parse error:", res.status, errText);
        alert(`Error al analizar la receta: ${errText}`);
        return;
      }
      const data = await res.json();
      onIngredientsFound(data.ingredients || []);
      setText("");
    } catch (err) {
      console.error("Recipe parse failed:", err);
      alert("Error de conexión al analizar la receta");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#1a3646] rounded-lg shadow-lg border border-[#2c6675] p-4">
      <h2 className="font-semibold text-lg mb-2 text-gray-100">
        🍳 Importar receta
      </h2>
      <p className="text-sm text-gray-400 mb-3">
        Pega una receta y la IA extraerá los ingredientes automáticamente
      </p>
      <textarea
        className="w-full bg-[#0e1626] border border-[#304a7d] rounded-md p-2 text-sm h-28 resize-none text-gray-200 placeholder-gray-500 focus:border-[#2c6675] focus:outline-none"
        placeholder="Pega aquí tu receta..."
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <button
        onClick={handleParse}
        disabled={loading || !text.trim()}
        className="mt-2 px-4 py-2 bg-orange-500 text-white rounded-md
                   hover:bg-orange-600 disabled:opacity-50 text-sm"
      >
        {loading ? "Analizando..." : "Extraer ingredientes"}
      </button>
    </div>
  );
}
