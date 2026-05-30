"""
LLM-powered product matching service.
Uses the LLM to rank search results by relevance and suggest substitutions.
"""

import json
from app.services.llm import LLMProvider

MATCH_PROMPT = """You are a grocery shopping assistant building an optimized shopping basket.
The user wants to buy: "{query}"

Hard constraints you MUST respect:
- Maximum different stores to visit: {max_shops}
- You MUST prefer products from stores that are already in the basket
  (stores already selected for other items). This minimises the number of shops.
- Only add a product from a NEW store if no acceptable match exists in the current stores.

Stores already chosen for this basket: {selected_stores}

Available products (already filtered to reachable stores within the travel time limit):
{products_json}

Relevance rules — be VERY strict. When in doubt, return no_exact_match=true rather than
returning a wrong product.

RAW MEAT & FISH — always fresh/raw, never pre-cooked or processed:
- "carne picada" = raw minced meat ONLY (bolsa de carne picada de ternera/cerdo/mixta)
  NOT canelones, albóndigas, hamburguesas, croquetas, lasaña, or any prepared dish with meat
- "pollo" = raw whole chicken or chicken pieces ONLY
  NOT broth, soup, nuggets, croquetas, or any processed chicken product
- General: any raw meat/fish query → the unprocessed ingredient itself. Reject anything
  pre-cooked, stuffed, marinated, breaded, or assembled into a dish.

FRESH PRODUCE — always the whole vegetable/fruit, never processed:
- "zanahorias" = fresh whole carrots or a bag of carrots ONLY
  NOT carrot snacks, NOT baby food, NOT juices, NOT animal food, NOT anything
  where carrot is a flavor or secondary ingredient
- "tomates pelados" = canned whole peeled tomatoes ONLY (not cherry, not sauce, not ketchup)
- "tomate triturado" = canned crushed/chopped tomato ONLY (not ketchup, not sauce, not whole)
- "espinacas" = fresh or frozen plain spinach ONLY (not spinach pasta, not spinach-filled products)
- General: any fresh vegetable/fruit query → reject snacks, soups, juices, sauces, baby food,
  flavored products, or anything where the vegetable is merely an ingredient or flavoring.

OILS — the oil itself, not foods made with it:
- "aceite de oliva" / "aceite" = a bottle or container of olive oil / cooking oil ONLY
  NOT colines, crackers, breadsticks, or any product that merely uses oil as an ingredient

DAIRY — the product itself:
- "queso rallado" = packaged shredded or grated cheese ONLY
  NOT cheese-flavored snacks, NOT crackers, NOT anything labelled "sabor queso"
- "leche" = liquid milk ONLY (not yogurt, cream, plant-based unless labelled "leche")

PANTRY:
- "pan" = bread ONLY (not breadcrumbs, crackers, toast, colines)
- "sal" = table/cooking salt ONLY (not salchichas, salmón, ensalada — reject any product
  that merely contains the letters "sal" in its name)
- "arroz" = uncooked rice ONLY (not rice crackers, rice milk, rice dishes)
- "ajo en polvo" = garlic powder ONLY (not fresh garlic, not garlic salt, not garlic sauce)
- "lasaña" / "pasta lasaña" / "tiras pasta lasaña" = dry lasagna pasta SHEETS only
  NOT cannelloni, NOT lasagna ready-meal, NOT other pasta shapes

GOLDEN RULE: match the INGREDIENT ITSELF as you would buy it in its raw or minimally
processed form. Reject anything where the ingredient is a flavoring, secondary component,
or part of a pre-assembled dish.

Your task:
1. From the list above, select ONLY products that genuinely match "{query}".
2. Among matching products, STRONGLY prefer those from: {selected_stores}
3. If a match exists in an already-selected store, return ONLY that match (ignore cheaper
   options in new stores — the travel cost outweighs small price differences).
4. If NO product is a good match at all, set no_exact_match=true and suggest the
   closest alternative.

Return ONLY this JSON, no other text:
{{
  "matches": [
    {{"product_id": "uuid", "name": "product name", "relevance": "high|medium"}}
  ],
  "no_exact_match": false,
  "suggestion": null
}}

If nothing matches:
{{
  "matches": [],
  "no_exact_match": true,
  "suggestion": {{
    "product_id": "uuid of closest alternative",
    "name": "product name",
    "reason": "brief explanation in Spanish"
  }}
}}"""


class ProductMatcher:
    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider

    async def match_products(
        self,
        query: str,
        candidates: list[dict],
        max_shops: int = 3,
        selected_stores: list[str] | None = None,
    ) -> dict:
        """
        Given a user query and a list of candidate products from the DB,
        use the LLM to rank by relevance and handle no-match cases.

        Returns:
            {
                "matches": [{"product_id": ..., "name": ..., "relevance": ...}],
                "no_exact_match": bool,
                "suggestion": {"product_id": ..., "name": ..., "reason": ...} | None
            }
        """
        if not candidates:
            return {
                "matches": [],
                "no_exact_match": True,
                "suggestion": None,
            }

        # Prepare a simplified product list for the LLM
        products_for_llm = [
            {
                "product_id": str(c["product_id"]),
                "name": c["name"],
                "price": float(c["price"]),
                "store_name": c.get("store_name", ""),
            }
            for c in candidates[:10]  # Keep small for local models
        ]

        stores_label = ", ".join(selected_stores) if selected_stores else "ninguna todavía"
        prompt = MATCH_PROMPT.format(
            query=query,
            max_shops=max_shops,
            selected_stores=stores_label,
            products_json=json.dumps(products_for_llm, ensure_ascii=False, indent=2),
        )

        print(f"\n[SmartMatch] 🔍 Query: \"{query}\"")
        print(f"[SmartMatch]    Candidates from DB: {len(products_for_llm)} products")
        for p in products_for_llm[:5]:
            print(f"[SmartMatch]      - {p['name']} ({p['price']:.2f}€ @ {p['store_name']})")
        if len(products_for_llm) > 5:
            print(f"[SmartMatch]      ... and {len(products_for_llm) - 5} more")

        try:
            response = await self.llm.parse_raw(prompt)

            # Log the LLM decision
            matches = response.get("matches", [])
            no_match = response.get("no_exact_match", False)
            suggestion = response.get("suggestion")

            if no_match:
                print(f"[SmartMatch] ❌ No exact match for \"{query}\"")
                if suggestion:
                    print(f"[SmartMatch] 💡 Suggestion: {suggestion.get('name', '?')}")
                    print(f"[SmartMatch]    Reason: {suggestion.get('reason', '?')}")
            else:
                print(f"[SmartMatch] ✅ LLM selected {len(matches)} products for \"{query}\":")
                for m in matches:
                    print(f"[SmartMatch]    → {m.get('name', '?')} (relevance: {m.get('relevance', '?')})")

            return response
        except Exception as e:
            print(f"[SmartMatch] ⚠ LLM call failed for \"{query}\": {e}")
            # Fallback: return all candidates as-is if LLM fails
            return {
                "matches": [
                    {"product_id": str(c["product_id"]), "name": c["name"], "relevance": "medium"}
                    for c in candidates[:10]
                ],
                "no_exact_match": False,
                "suggestion": None,
            }
