"""
agents.py
---------
Two-agent system for IAbuela grocery optimization.
Runs locally via Ollama (qwen2.5-coder:7b-instruct-q4_K_M).

Agent 1 – Shopping Optimizer
  Given a budget, item categories, number of people, and max shops,
  queries iabuela_catalog.db and builds the cheapest basket.
  Uses a `finalize_basket` terminal tool so the orchestrator gets
  structured data (shop list) to hand off to Agent 2.

Agent 2 – Route Optimizer
  Given the selected shops and a max distance / duration limit,
  replicates the ORS API calls from iabuela-route-optimizer.html
  (geocode → VRP optimize → directions) to compute the optimal route.
  Drops the most distant shop and re-optimises if limits are exceeded.

Orchestrator
  Runs both agents in sequence and prints the combined plan.

Requirements:
  pip install ollama
  ollama pull qwen2.5-coder:7b-instruct-q4_K_M

Usage:
  python agents.py
"""

import json
import os
import sqlite3
import ssl
import urllib.parse
import urllib.request

import ollama

# ── Config ─────────────────────────────────────────────────────────────────────

MODEL       = "qwen2.5-coder:7b-instruct-q4_K_M"
DB_PATH     = "iabuela_catalog.db"
ORS_BASE    = "https://api.openrouteservice.org"
APIKEY_PATH = "my_apikey.json"
HTML_PATH   = "iabuela-route-optimizer.html"


def _load_ors_key() -> str:
    """Read the ORS API key from my_apikey.json, falling back to ORS_API_KEY env var."""
    try:
        with open(APIKEY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return os.getenv("ORS_API_KEY", "")

# ── HTTP helper ────────────────────────────────────────────────────────────────

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode    = ssl.CERT_NONE


def _http(url: str, method: str = "GET", body: dict = None, headers: dict = None) -> dict:
    data = json.dumps(body).encode() if body else None
    h = {"Content-Type": "application/json; charset=utf-8", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, context=_SSL, timeout=20) as resp:
        return json.loads(resp.read().decode())


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


# ── Generic agent loop ─────────────────────────────────────────────────────────

def _parse_text_tool_calls(content: str) -> list[dict]:
    """
    Fallback: some models emit tool calls as plain JSON text rather than using
    the native tool_calls field. Extracts {name, arguments} objects from text.

    Uses a brace-depth tracker (not regex) so it handles arbitrarily nested JSON
    such as arguments containing arrays of objects.
    """
    # Try the whole content as a single JSON object first
    try:
        obj = json.loads(content.strip())
        if isinstance(obj, dict) and "name" in obj:
            return [{"name": obj["name"], "arguments": obj.get("arguments", {})}]
    except (json.JSONDecodeError, ValueError):
        pass

    calls = []
    i = 0
    while i < len(content):
        if content[i] != '{':
            i += 1
            continue

        # Walk forward tracking brace depth, respecting strings and escapes
        depth = 0
        in_str = False
        escaped = False
        for j in range(i, len(content)):
            ch = content[j]
            if escaped:
                escaped = False
                continue
            if ch == '\\' and in_str:
                escaped = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(content[i:j + 1])
                        if isinstance(obj, dict) and "name" in obj:
                            calls.append({
                                "name":      obj["name"],
                                "arguments": obj.get("arguments", {}),
                            })
                    except (json.JSONDecodeError, ValueError):
                        pass
                    i = j + 1
                    break
        else:
            i += 1

    return calls


def _dispatch(name: str, args: dict, tool_fns: dict, terminal_tool: str | None) -> tuple[dict, bool, bool]:
    """Execute a tool call. Returns (result, is_terminal, is_unknown)."""
    if name == terminal_tool:
        return {"status": "ok"}, True, False
    fn = tool_fns.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}, False, True
    try:
        return fn(**args), False, False
    except Exception as exc:
        return {"error": str(exc)}, False, False


def _run_agent(
    system: str,
    user_msg: str,
    tools: list[dict],
    tool_fns: dict,
    terminal_tool: str | None = None,
) -> tuple[str, dict | None]:
    """
    Runs the Ollama tool-use loop.
    Returns (final_text, terminal_result).
    terminal_result is the dict passed to `terminal_tool`, or None.

    Handles two modes:
      - Native tool_calls: model populates msg.tool_calls (preferred).
      - Text fallback: model emits JSON tool calls inside msg.content.

    Breaks immediately if the model only calls unknown/hallucinated tools so it
    cannot get stuck in an error loop.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_msg},
    ]
    final_text: str = ""
    terminal_result: dict | None = None

    while True:
        response = ollama.chat(model=MODEL, messages=messages, tools=tools)
        msg = response.message

        # ── Native tool_calls path ─────────────────────────────────────────
        if msg.tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            all_unknown = True
            for tc in msg.tool_calls:
                name = tc.function.name
                args = tc.function.arguments
                result, is_terminal, is_unknown = _dispatch(name, args, tool_fns, terminal_tool)
                if is_terminal:
                    terminal_result = args
                if not is_unknown:
                    all_unknown = False
                messages.append({"role": "tool", "content": json.dumps(result, ensure_ascii=False)})
            if all_unknown:
                # Model hallucinated tools — collect any inline text and stop
                final_text = msg.content or ""
                break

        # ── Text fallback path ─────────────────────────────────────────────
        else:
            parsed = _parse_text_tool_calls(msg.content or "")
            if parsed:
                messages.append({"role": "assistant", "content": msg.content or ""})
                result_parts = []
                all_unknown = True
                for call in parsed:
                    name = call["name"]
                    args = call["arguments"]
                    result, is_terminal, is_unknown = _dispatch(name, args, tool_fns, terminal_tool)
                    if is_terminal:
                        terminal_result = args
                    if not is_unknown:
                        all_unknown = False
                    result_parts.append(
                        f"Tool result for {name}:\n{json.dumps(result, ensure_ascii=False)}"
                    )
                if all_unknown:
                    final_text = msg.content or ""
                    break
                messages.append({
                    "role": "user",
                    "content": "\n\n".join(result_parts) + "\n\nContinue.",
                })
            else:
                final_text = msg.content or ""
                break

    return final_text, terminal_result


# ══════════════════════════════════════════════════════════════════════════════
#  SHOPPING OPTIMIZER  (pure Python — no LLM)
# ══════════════════════════════════════════════════════════════════════════════

def _query_products(keyword: str) -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        """SELECT p.product_id, p.name, p.sku, p.price,
                  s.shop_id, s.name AS shop_name, s.chain, s.address
           FROM products p
           JOIN shops s ON p.shop_id = s.shop_id
           WHERE LOWER(p.name) LIKE ?
           ORDER BY p.price ASC
           LIMIT 10""",
        (f"%{keyword.lower()}%",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def run_shopping_agent(
    budget: float,
    categories: list[str],
    n_people: int,
    max_shops: int,
) -> tuple[str, dict | None]:
    """
    Greedy Python optimizer — no LLM calls, runs in milliseconds.

    For each category picks the cheapest product, consolidating into the fewest
    shops (up to max_shops). Budget is a soft target: all categories are always
    included even if the total exceeds it.
    """
    # Fetch cheapest candidates for every category in one DB round-trip each
    candidates: dict[str, list[dict]] = {}
    for cat in categories:
        rows = _query_products(cat)
        if rows:
            candidates[cat] = rows
        else:
            print(f"  ⚠ No products found for category '{cat}' — skipped.")

    selected_shops: set[int] = set()
    items: list[dict] = []

    # Sort categories so rarest (fewest candidates) are picked first,
    # giving the greedy pass more flexibility for common ones.
    ordered_cats = sorted(candidates, key=lambda c: len(candidates[c]))

    for cat in ordered_cats:
        rows = candidates[cat]

        # Prefer a shop already in the basket; open a new slot only if there is room
        match = next((r for r in rows if r["shop_id"] in selected_shops), None)
        if match is None:
            if len(selected_shops) < max_shops:
                match = rows[0]          # cheapest overall, opens a new shop
            else:
                # All shop slots used — pick cheapest that fits an existing shop
                # (may not exist → fall back to cheapest, exceeding max_shops)
                match = next((r for r in rows if r["shop_id"] in selected_shops), rows[0])

        selected_shops.add(match["shop_id"])

        # Scale quantity: 1 per person for cheap perishables, 1 total otherwise
        qty = n_people if match["price"] < 3.0 else 1
        items.append({
            "shop_id":      match["shop_id"],
            "shop_name":    match["shop_name"],
            "product_name": match["name"],
            "unit_price":   match["price"],
            "quantity":     qty,
            "line_total":   round(match["price"] * qty, 2),
        })

    if not items:
        return "", None

    total = round(sum(i["line_total"] for i in items), 2)
    over  = total > budget
    basket = {
        "items":      items,
        "total_cost": total,
        "shops_used": list(selected_shops),
    }

    summary = (f"Basket: {len(items)} products across {len(selected_shops)} shop(s), "
               f"total {total:.2f}€"
               + (f" (⚠ {total - budget:.2f}€ over budget)" if over else " (within budget)"))
    return summary, basket


# ══════════════════════════════════════════════════════════════════════════════
#  AGENT 2 — ROUTE OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════

_ROUTE_SYSTEM = """\
You are a route planning assistant. The route is always circular: it starts at
the client's home, visits the shops in the optimal order, and returns to home.

Given a home address, a list of shops (each with name, lat, lng, basket_cost),
a transport mode, and distance / duration limits, follow these steps:

1. Call geocode_address to get coordinates for the home address.
2. Call optimize_route with all shops. The tool returns ordered_stops,
   distance_km, and duration_min.
3. If both limits are met → write your summary as plain text and stop.
   Do NOT call any additional tool after the route fits.
4. Otherwise drop the last shop and call optimize_route again with the reduced
   list. Repeat until the route fits or only one shop remains.
5. If even a single-shop route exceeds the max_duration_min limit:
   a. Call get_shop_travel_times to get the round-trip duration from home to
      each shop individually.
   b. Identify the CLOSEST shop (lowest duration_min) and the CHEAPEST shop
      (lowest basket_cost).
   c. Write your summary as plain text with two options clearly labelled
      "Option A – Closest" and "Option B – Cheapest".
      Do NOT call any additional tool after this.
"""

_ROUTE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_shop_travel_times",
            "description": (
                "Use the ORS Matrix API to get the round-trip travel duration and distance "
                "from home to each shop individually. Use this when all routes exceed limits "
                "to identify the closest and cheapest alternatives."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "home_lat":       {"type": "number"},
                    "home_lng":       {"type": "number"},
                    "shops": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name":        {"type": "string"},
                                "lat":         {"type": "number"},
                                "lng":         {"type": "number"},
                                "basket_cost": {"type": "number"},
                            },
                            "required": ["name", "lat", "lng"],
                        },
                    },
                    "transport_mode": {
                        "type": "string",
                        "enum": ["driving-car", "cycling-regular", "foot-walking"],
                    },
                    "api_key": {"type": "string"},
                },
                "required": ["home_lat", "home_lng", "shops", "transport_mode", "api_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "geocode_address",
            "description": "Geocode a Spanish street address to lat/lng via OpenRouteService.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "api_key": {"type": "string"},
                },
                "required": ["address", "api_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_route",
            "description": (
                "Compute the optimal circular route: home → shops (best order) → home, "
                "using ORS VRP + directions. "
                "Returns ordered_stops (home first and last), distance_km, duration_min."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "home_lat":     {"type": "number"},
                    "home_lng":     {"type": "number"},
                    "home_address": {"type": "string", "description": "Label for the home stop"},
                    "shops": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name":    {"type": "string"},
                                "address": {"type": "string"},
                                "lat":     {"type": "number"},
                                "lng":     {"type": "number"},
                            },
                            "required": ["name", "lat", "lng"],
                        },
                    },
                    "transport_mode": {
                        "type": "string",
                        "enum": ["driving-car", "cycling-regular", "foot-walking"],
                    },
                    "api_key": {"type": "string"},
                },
                "required": ["home_lat", "home_lng", "shops", "transport_mode", "api_key"],
            },
        },
    },
]


def _get_shop_travel_times(
    home_lat: float,
    home_lng: float,
    shops: list[dict],
    transport_mode: str,
    api_key: str,
) -> list[dict]:
    """
    ORS Matrix API: one call to get home→shop→home round-trip for every shop.
    Returns each shop annotated with duration_min and distance_km.
    """
    locations = [[home_lng, home_lat]] + [[s["lng"], s["lat"]] for s in shops]
    body = {
        "locations":    locations,
        "metrics":      ["duration", "distance"],
        "sources":      [0],
        "destinations": list(range(1, len(shops) + 1)),
    }
    data = _http(
        f"{ORS_BASE}/v2/matrix/{transport_mode}/json",
        method="POST",
        body=body,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
    )
    durations = data["durations"][0]   # seconds from home to each shop
    distances = data["distances"][0]   # metres from home to each shop

    result = []
    for i, shop in enumerate(shops):
        one_way_s = durations[i]
        one_way_m = distances[i]
        result.append({
            "name":         shop["name"],
            "basket_cost":  shop.get("basket_cost", 0),
            "duration_min": round(one_way_s * 2 / 60, 1),   # round-trip
            "distance_km":  round(one_way_m * 2 / 1000, 2), # round-trip
        })
    return sorted(result, key=lambda x: x["duration_min"])


def _geocode(address: str, api_key: str) -> dict:
    url = (
        f"{ORS_BASE}/geocode/search"
        f"?api_key={urllib.parse.quote(api_key)}"
        f"&text={urllib.parse.quote(address)}"
        f"&size=1&boundary.country=ES&lang=es"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "IAbuela/1.0"})
    with urllib.request.urlopen(req, context=_SSL, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    if not data.get("features"):
        return {"error": f"Address not found: {address}"}
    feat = data["features"][0]
    lng, lat = feat["geometry"]["coordinates"]
    return {"lat": lat, "lng": lng, "label": feat["properties"].get("label", address)}


def _optimize_route(
    home_lat: float,
    home_lng: float,
    shops: list[dict],
    transport_mode: str,
    api_key: str,
    home_address: str = "Home",
) -> dict:
    """
    Replicates optimizeVRP + directions from iabuela-route-optimizer.html in Python.
    Route is circular: starts at home, visits all shops in optimal order, returns home.
    """
    if not shops:
        return {"error": "No shops provided"}

    auth = {"Authorization": api_key}

    # VRP: find optimal visit order (vehicle starts AND ends at home → circular)
    jobs = [{"id": i + 1, "location": [s["lng"], s["lat"]]} for i, s in enumerate(shops)]
    vrp = _http(
        f"{ORS_BASE}/optimization",
        method="POST",
        body={
            "jobs": jobs,
            "vehicles": [{"id": 1, "profile": transport_mode,
                          "start": [home_lng, home_lat], "end": [home_lng, home_lat]}],
        },
        headers={**auth, "Content-Type": "application/json"},
    )

    ordered: list[dict] = []
    for step in vrp["routes"][0].get("steps", []):
        if step["type"] == "job":
            ordered.append(shops[step["id"] - 1])

    # Directions: home → shops (optimal order) → home
    coords = ([[home_lng, home_lat]]
              + [[s["lng"], s["lat"]] for s in ordered]
              + [[home_lng, home_lat]])
    directions = _http(
        f"{ORS_BASE}/v2/directions/{transport_mode}/geojson",
        method="POST",
        body={"coordinates": coords, "geometry": False, "instructions": False},
        headers={**auth, "Content-Type": "application/json; charset=utf-8"},
    )
    summary = directions["features"][0]["properties"]["summary"]

    home_stop = {"name": f"🏠 {home_address}", "lat": home_lat, "lng": home_lng}
    return {
        "ordered_stops": (
            [home_stop]
            + [{"name": s["name"], "address": s.get("address", ""), "lat": s["lat"], "lng": s["lng"]}
               for s in ordered]
            + [home_stop]
        ),
        "distance_km":  round(summary["distance"] / 1000, 2),
        "duration_min": round(summary["duration"] / 60,  1),
    }


_ROUTE_FNS = {
    "get_shop_travel_times": lambda **kw: _get_shop_travel_times(**kw),
    "geocode_address":       lambda address, api_key, **_: _geocode(address, api_key),
    "optimize_route":        lambda **kw: _optimize_route(**kw),
}


def run_route_agent(
    home_address: str,
    shops: list[dict],
    transport_mode: str,
    max_distance_km: float,
    max_duration_min: float,
    ors_api_key: str,
) -> str:
    """Returns a text report of the optimized route."""
    user_msg = (
        f"Plan the shopping route:\n"
        f"- Home: {home_address}\n"
        f"- Shops: {json.dumps(shops, ensure_ascii=False)}\n"
        f"- Transport: {transport_mode}\n"
        f"- Max distance: {max_distance_km} km\n"
        f"- Max duration: {max_duration_min} min\n"
        f"- ORS API key: {ors_api_key}\n"
        "Geocode home, optimize the route, drop shops if limits are exceeded, report."
    )
    text, _ = _run_agent(
        system=_ROUTE_SYSTEM,
        user_msg=user_msg,
        tools=_ROUTE_TOOLS,
        tool_fns=_ROUTE_FNS,
    )
    return text


# ── HTML launcher ─────────────────────────────────────────────────────────────

def _launch_html(
    home_address: str,
    shops: list[dict],
    transport_mode: str,
    api_key: str = "",
    html_path: str = HTML_PATH,
) -> None:
    """
    Open iabuela-route-optimizer.html in the default browser with the route
    stops pre-filled via URL query parameters.

    Stops order: home → shop addresses → home (circular).
    The HTML reads ?stop=...&stop=...&mode=...&apikey=... on load.
    The API key is always sourced from my_apikey.json (falls back to the
    api_key argument if the file is missing).
    """
    import webbrowser

    key = _load_ors_key() or api_key

    stops = (
        [home_address]
        + [s["address"] for s in shops]
        + [home_address]
    )
    params = urllib.parse.urlencode(
        [("stop", s) for s in stops] + [("mode", transport_mode), ("apikey", key)],
        quote_via=urllib.parse.quote,
    )
    abs_path = os.path.abspath(html_path)
    url = f"file:///{abs_path.replace(os.sep, '/')}?{params}"
    print(f"\n  Opening route optimizer in browser...")
    webbrowser.open(url)


# ══════════════════════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

def orchestrate(
    budget: float,
    categories: list[str],
    n_people: int,
    max_shops: int,
    home_address: str,
    transport_mode: str,        # "driving-car" | "cycling-regular" | "foot-walking"
    max_distance_km: float,
    max_duration_min: float,
    ors_api_key: str,
) -> None:
    print("\n" + "═" * 72)
    print("  IAbuela · Multi-Agent Shopping & Route Optimizer")
    print(f"  Model: {MODEL}")
    print("═" * 72)
    print(f"  Budget: {budget:.2f}€  |  People: {n_people}  |  Max shops: {max_shops}")
    print(f"  Categories: {', '.join(categories)}")
    print(f"  Transport: {transport_mode}  |  Limit: {max_distance_km} km / {max_duration_min} min")
    print("─" * 72)

    # ── Agent 1: Shopping optimizer ────────────────────────────────────────
    print("\n[Agent 1] Shopping Optimizer — building basket...\n")
    text_report, basket = run_shopping_agent(budget, categories, n_people, max_shops)

    if basket is None:
        print("  ⚠ Shopping agent did not finalize a basket.")
        if text_report:
            print(text_report)
        return

    # Model sometimes passes the items list directly instead of {items: [...]}
    if isinstance(basket, list):
        basket = {"items": basket}
    elif "items" not in basket:
        # Arguments dict is itself the single item
        basket = {"items": [basket]}

    # Normalise items — model may omit optional computed fields
    for it in basket["items"]:
        it.setdefault("quantity",   1)
        it.setdefault("unit_price", it.get("price", 0.0))
        it.setdefault("line_total", round(it["unit_price"] * it["quantity"], 2))
        it.setdefault("shop_name",  f"Shop {it.get('shop_id', '?')}")

    # Derive total_cost and shops_used if the model skipped them
    if not basket.get("total_cost"):
        basket["total_cost"] = round(sum(i["line_total"] for i in basket["items"]), 2)
    if not basket.get("shops_used"):
        basket["shops_used"] = list({i["shop_id"] for i in basket["items"] if "shop_id" in i})

    # Print basket grouped by shop
    by_shop: dict[str, list] = {}
    for item in basket["items"]:
        by_shop.setdefault(item["shop_name"], []).append(item)

    for shop_name, items in by_shop.items():
        print(f"  📍 {shop_name}")
        for it in items:
            print(f"     {it['product_name']:<42} {it['quantity']}x {it['unit_price']:.2f}€"
                  f"  = {it['line_total']:.2f}€")
    print(f"\n  Total: {basket['total_cost']:.2f}€  |  Shops: {len(by_shop)}")

    # ── Resolve shop coordinates from DB + attach basket cost per shop ────
    used_ids = basket["shops_used"]
    shop_cost: dict[int, float] = {}
    for it in basket["items"]:
        sid = it.get("shop_id")
        if sid is not None:
            shop_cost[sid] = round(shop_cost.get(sid, 0.0) + it["line_total"], 2)

    conn = _conn()
    rows = conn.execute(
        f"SELECT shop_id, name, address, latitude AS lat, longitude AS lng "
        f"FROM shops WHERE shop_id IN ({','.join('?' * len(used_ids))})",
        used_ids,
    ).fetchall()
    conn.close()
    shops_for_route = [
        {
            "name":        r["name"],
            "address":     r["address"],
            "lat":         r["lat"],
            "lng":         r["lng"],
            "basket_cost": shop_cost.get(r["shop_id"], 0.0),
        }
        for r in rows
    ]

    if not ors_api_key:
        print("\n  ⚠ ORS_API_KEY not set — skipping route optimization.")
        print("    Set it with:  set ORS_API_KEY=<your_key>  (Windows)")
        return

    # ── Agent 2: Route optimizer ───────────────────────────────────────────
    print("\n\n[Agent 2] Route Optimizer — computing optimal route...\n")
    route_report = run_route_agent(
        home_address=home_address,
        shops=shops_for_route,
        transport_mode=transport_mode,
        max_distance_km=max_distance_km,
        max_duration_min=max_duration_min,
        ors_api_key=ors_api_key,
    )
    print(route_report)
    print("\n" + "═" * 72)

    _launch_html(
        home_address=home_address,
        shops=shops_for_route,
        transport_mode=transport_mode,
        api_key=ors_api_key,
    )


# ── Demo ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    orchestrate(
        budget=35.0,
        categories=["leche", "pan", "aceite", "pasta", "arroz", "agua", "huevos", "pollo"],
        n_people=3,
        max_shops=2,
        home_address="Puerta del Sol, Madrid",
        transport_mode="driving-car",
        max_distance_km=12.0,
        max_duration_min=40.0,
        ors_api_key=_load_ors_key(),
    )
