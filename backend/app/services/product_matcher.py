"""
LLM-powered product matching service.
Uses the LLM to rank search results by relevance and suggest substitutions.
"""

import json
from app.services.llm import LLMProvider

MATCH_PROMPT = """You are a grocery shopping assistant. The user wants to buy: "{query}"

Here are the products available in nearby stores:
{products_json}

Your task:
1. Select the products that BEST match what the user is looking for.
   - "leche" means milk (liquid milk), NOT yogurt, NOT cheese, NOT cream
   - "pan" means bread, NOT breadcrumbs, NOT toast
   - "pollo" means chicken meat, NOT chicken soup, NOT chicken broth
   - Be strict: only include products the user would actually want
2. If NONE of the products are a good match, suggest the closest alternative
   and explain why.

Return a JSON object with this structure:
{{
  "matches": [
    {{"product_id": "uuid", "name": "product name", "relevance": "high|medium"}},
  ],
  "no_exact_match": false,
  "suggestion": null
}}

If nothing matches well:
{{
  "matches": [],
  "no_exact_match": true,
  "suggestion": {{
    "product_id": "uuid of closest alternative",
    "name": "product name",
    "reason": "brief explanation in Spanish of why this is a good substitute"
  }}
}}

Return ONLY the JSON, no other text."""


class ProductMatcher:
    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider

    async def match_products(self, query: str, candidates: list[dict]) -> dict:
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

        prompt = MATCH_PROMPT.format(
            query=query,
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
