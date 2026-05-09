"""
agents_v2.py
------------
Two-agent system for IAbuela grocery optimization.
Runs locally via Ollama (qwen2.5-coder:7b-instruct-q4_K_M).
Built with LangChain + LangGraph for proper agentic tool-use loops.

Agent 1 – Shopping Optimizer  (deterministic Python, no LLM)
  Given a budget, item categories, number of people, and max shops,
  queries iabuela_catalog.db and builds the cheapest basket.

Agent 2 – Route Optimizer  (LLM-driven, LangGraph tool-use loop)
  Geocodes home, runs ORS VRP + directions, drops shops until the
  distance/duration limits are met, falls back to the matrix API if needed.

Orchestrator
  LangGraph StateGraph that pipes both agents in sequence.

Requirements:
  pip install langchain-ollama langgraph langchain-core
  ollama pull qwen2.5-coder:7b-instruct-q4_K_M
"""

import json
import operator
import os
import sqlite3
import ssl
import urllib.parse
import urllib.request
import webbrowser
from typing import Annotated, List, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph

# ── Config ─────────────────────────────────────────────────────────────────────

MODEL       = "qwen2.5-coder:7b-instruct-q4_K_M"
DB_PATH     = "iabuela_catalog.db"
ORS_BASE    = "https://api.openrouteservice.org"
APIKEY_PATH = "my_apikey.json"
HTML_PATH   = "iabuela-route-optimizer.html"
BROWSER     = "chrome"   # "chrome" | "firefox" | "edge" | "" = system default


def _load_ors_key() -> str:
    """Read the ORS API key from my_apikey.json, falling back to ORS_API_KEY env var."""
    try:
        with open(APIKEY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return os.getenv("ORS_API_KEY", "")


# ── HTTP + SSL ─────────────────────────────────────────────────────────────────

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode    = ssl.CERT_NONE


def _http(url: str, method: str = "GET", body: dict = None, headers: dict = None) -> dict:
    data = json.dumps(body).encode() if body else None
    h = {"Content-Type": "application/json; charset=utf-8", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, context=_SSL, timeout=20) as resp:
        return json.loads(resp.read().decode())


# ── DB ─────────────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


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


# ── LangChain Tools ────────────────────────────────────────────────────────────

@tool
def geocode_address(address: str, api_key: str) -> dict:
    """Geocode a Spanish street address to lat/lng via OpenRouteService."""
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


@tool
def optimize_route(
    home_lat: float,
    home_lng: float,
    home_address: str,
    shops: List[dict],
    transport_mode: str,
    api_key: str,
) -> dict:
    """
    Compute the optimal circular route: home → shops (best order) → home,
    using ORS VRP + directions. Returns ordered_stops, distance_km, duration_min.
    home_address is used as a label for the home stop in the output.
    """
    if not shops:
        return {"error": "No shops provided"}

    auth = {"Authorization": api_key}
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
        "duration_min": round(summary["duration"] / 60, 1),
    }


@tool
def get_shop_travel_times(
    home_lat: float,
    home_lng: float,
    shops: List[dict],
    transport_mode: str,
    api_key: str,
) -> List[dict]:
    """
    ORS Matrix API: round-trip travel duration and distance from home to each
    shop individually. Use this when all multi-stop routes exceed the limits to
    identify the closest (lowest duration_min) and cheapest (lowest basket_cost)
    alternatives. Returns a list sorted by duration_min ascending.
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
    durations = data["durations"][0]
    distances = data["distances"][0]
    result = []
    for i, shop in enumerate(shops):
        result.append({
            "name":         shop["name"],
            "basket_cost":  shop.get("basket_cost", 0),
            "duration_min": round(durations[i] * 2 / 60, 1),
            "distance_km":  round(distances[i] * 2 / 1000, 2),
        })
    return sorted(result, key=lambda x: x["duration_min"])


_ROUTE_TOOLS = [geocode_address, optimize_route, get_shop_travel_times]
_TOOL_MAP    = {t.name: t for t in _ROUTE_TOOLS}


# ── State ──────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    budget:          float
    categories:      List[str]
    n_people:        int
    max_shops:       int
    home_address:    str
    transport_mode:  str
    max_dist:        float
    max_dur:         float
    ors_key:         str
    basket:          dict
    shops_for_route: List[dict]
    route_messages:  Annotated[List[BaseMessage], operator.add]
    route_report:    str


# ══════════════════════════════════════════════════════════════════════════════
#  NODE 1 – SHOPPING OPTIMIZER  (greedy Python, no LLM)
# ══════════════════════════════════════════════════════════════════════════════

def shopping_node(state: AgentState) -> dict:
    """
    Greedy optimizer: for each category picks the cheapest product, consolidating
    into the fewest shops (up to max_shops). Budget is a soft target.
    """
    budget     = state["budget"]
    categories = state["categories"]
    n_people   = state["n_people"]
    max_shops  = state["max_shops"]

    candidates: dict[str, list[dict]] = {}
    for cat in categories:
        rows = _query_products(cat)
        if rows:
            candidates[cat] = rows
        else:
            print(f"  ⚠ No products found for category '{cat}' — skipped.")

    selected_shops: set[int] = set()
    items: list[dict] = []

    # Sort rarest categories first so the greedy pass has more flexibility.
    ordered_cats = sorted(candidates, key=lambda c: len(candidates[c]))

    for cat in ordered_cats:
        rows = candidates[cat]
        match = next((r for r in rows if r["shop_id"] in selected_shops), None)
        if match is None:
            if len(selected_shops) < max_shops:
                match = rows[0]
            else:
                match = next((r for r in rows if r["shop_id"] in selected_shops), rows[0])
        selected_shops.add(match["shop_id"])
        qty = n_people if match["price"] < 3.0 else 1
        items.append({
            "shop_id":      match["shop_id"],
            "shop_name":    match["shop_name"],
            "product_name": match["name"],
            "unit_price":   match["price"],
            "quantity":     qty,
            "line_total":   round(match["price"] * qty, 2),
        })

    total = round(sum(i["line_total"] for i in items), 2) if items else 0.0
    over  = total > budget

    by_shop: dict[str, list] = {}
    for item in items:
        by_shop.setdefault(item["shop_name"], []).append(item)

    for shop_name, shop_items in by_shop.items():
        print(f"  📍 {shop_name}")
        for it in shop_items:
            print(f"     {it['product_name']:<42} {it['quantity']}x {it['unit_price']:.2f}€"
                  f"  = {it['line_total']:.2f}€")

    print(f"\n  Total: {total:.2f}€  |  Shops: {len(by_shop)}"
          + (f"  ⚠ ({total - budget:.2f}€ over budget)" if over else ""))

    return {
        "basket": {
            "items":      items,
            "total_cost": total,
            "shops_used": list(selected_shops),
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
#  NODE 2 – PREPARE ROUTE  (resolve DB coords, seed initial messages)
# ══════════════════════════════════════════════════════════════════════════════

_ROUTE_SYSTEM = (
    "You are a route planning assistant. The route is always circular: it starts at "
    "the client's home, visits the shops in the optimal order, and returns to home.\n\n"
    "Given a home address, a list of shops (each with name, lat, lng, basket_cost), "
    "a transport mode, and distance / duration limits, follow these steps:\n\n"
    "1. Call geocode_address to get coordinates for the home address.\n"
    "2. Call optimize_route with all shops. The tool returns ordered_stops, "
    "distance_km, and duration_min.\n"
    "3. If both limits are met → write your summary as plain text and stop.\n"
    "   Do NOT call any additional tool after the route fits.\n"
    "4. Otherwise drop the last shop and call optimize_route again with the reduced "
    "list. Repeat until the route fits or only one shop remains.\n"
    "5. If even a single-shop route exceeds the max_duration_min limit:\n"
    "   a. Call get_shop_travel_times to get the round-trip duration from home to "
    "each shop individually.\n"
    "   b. Identify the CLOSEST shop (lowest duration_min) and the CHEAPEST shop "
    "(lowest basket_cost).\n"
    "   c. Write your summary as plain text with two options clearly labelled "
    "'Option A – Closest' and 'Option B – Cheapest'.\n"
    "      Do NOT call any additional tool after this."
)


def prepare_route_node(state: AgentState) -> dict:
    basket  = state["basket"]
    ors_key = state["ors_key"]

    if not ors_key:
        print("\n  ⚠ ORS_API_KEY not set — skipping route optimization.")
        print("    Set it with:  set ORS_API_KEY=<your_key>  (Windows)")
        return {"shops_for_route": [], "route_messages": []}

    used_ids = basket.get("shops_used", [])
    if not used_ids:
        return {"shops_for_route": [], "route_messages": []}

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

    print("\n\n[Agent 2] Route Optimizer — computing optimal route...\n")

    user_msg = HumanMessage(content=(
        f"Plan the shopping route:\n"
        f"- Home: {state['home_address']}\n"
        f"- Shops: {json.dumps(shops_for_route, ensure_ascii=False)}\n"
        f"- Transport: {state['transport_mode']}\n"
        f"- Max distance: {state['max_dist']} km\n"
        f"- Max duration: {state['max_dur']} min\n"
        f"- ORS API key: {ors_key}\n"
        "Geocode home, optimize the route, drop shops if limits are exceeded, report."
    ))

    return {
        "shops_for_route": shops_for_route,
        "route_messages":  [SystemMessage(content=_ROUTE_SYSTEM), user_msg],
    }


# ══════════════════════════════════════════════════════════════════════════════
#  NODES 3a / 3b – ROUTE LLM  ↔  ROUTE TOOLS  (loop until done)
# ══════════════════════════════════════════════════════════════════════════════

_route_llm = ChatOllama(model=MODEL, temperature=0).bind_tools(_ROUTE_TOOLS)


def route_llm_node(state: AgentState) -> dict:
    """Calls the LLM with the full route message history."""
    response = _route_llm.invoke(state["route_messages"])
    return {"route_messages": [response]}


def route_tools_node(state: AgentState) -> dict:
    """Executes every tool call in the latest AI message and appends ToolMessages."""
    last = state["route_messages"][-1]
    tool_messages: list[ToolMessage] = []
    for tc in last.tool_calls:
        fn = _TOOL_MAP.get(tc["name"])
        try:
            result = fn.invoke(tc["args"]) if fn else {"error": f"Unknown tool: {tc['name']}"}
        except Exception as exc:
            result = {"error": str(exc)}
        tool_messages.append(ToolMessage(
            content=json.dumps(result, ensure_ascii=False),
            tool_call_id=tc["id"],
        ))
    return {"route_messages": tool_messages}


def should_continue_route(state: AgentState) -> str:
    last = state["route_messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "route_tools"
    return "finalize_route"


def should_run_route(state: AgentState) -> str:
    return "route_llm" if (state["shops_for_route"] and state["ors_key"]) else "end"


# ══════════════════════════════════════════════════════════════════════════════
#  NODE 4 – FINALIZE ROUTE  (print report + separator)
# ══════════════════════════════════════════════════════════════════════════════

def finalize_route_node(state: AgentState) -> dict:
    last   = state["route_messages"][-1]
    report = last.content if hasattr(last, "content") else ""
    print(report)
    print("\n" + "═" * 72)
    return {"route_report": report}


# ── HTML launcher ──────────────────────────────────────────────────────────────

_WIN_EXE = {
    "chrome":  [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
    "firefox": [r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"],
    "edge":    [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"],
}


_NEW_WINDOW_FLAG = {"chrome": "--new-window", "firefox": "-new-window", "edge": "--new-window"}


def _open_url(url: str) -> None:
    import subprocess
    if not BROWSER:
        webbrowser.open_new_tab(url)
        return
    candidates = _WIN_EXE.get(BROWSER.lower(), [BROWSER])
    exe = next((p for p in candidates if os.path.isfile(p)), None)
    if exe:
        flag = _NEW_WINDOW_FLAG.get(BROWSER.lower())
        cmd  = [exe, flag, url] if flag else [exe, url]
        subprocess.Popen(cmd)
    else:
        try:
            webbrowser.get(BROWSER).open_new_tab(url)
        except webbrowser.Error:
            webbrowser.open_new_tab(url)


def _launch_html(
    home_address: str,
    shops: List[dict],
    transport_mode: str,
    api_key: str = "",
    html_path: str = HTML_PATH,
) -> None:
    import time
    key = _load_ors_key() or api_key

    # Write session data to a JS file so Chrome always reads fresh data from disk
    stops_list = [home_address] + [s["address"] for s in shops] + [home_address]
    session_js = os.path.join(os.path.dirname(os.path.abspath(html_path)), "route_session.js")
    with open(session_js, "w", encoding="utf-8") as f:
        f.write(f"window.ROUTE_SESSION={json.dumps({'stops': stops_list, 'mode': transport_mode, 'apikey': key}, ensure_ascii=False)};")

    abs_path = os.path.abspath(html_path)
    url = f"file:///{abs_path.replace(os.sep, '/')}?_t={int(time.time())}"
    print(f"\n  Opening route optimizer in browser...")
    _open_url(url)


# ── LangGraph ─────────────────────────────────────────────────────────────────

builder = StateGraph(AgentState)
builder.add_node("build_basket",   shopping_node)
builder.add_node("prepare_route",  prepare_route_node)
builder.add_node("route_llm",      route_llm_node)
builder.add_node("route_tools",    route_tools_node)
builder.add_node("finalize_route", finalize_route_node)

builder.set_entry_point("build_basket")
builder.add_edge("build_basket",  "prepare_route")
builder.add_conditional_edges(
    "prepare_route", should_run_route,
    {"route_llm": "route_llm", "end": END},
)
builder.add_conditional_edges(
    "route_llm", should_continue_route,
    {"route_tools": "route_tools", "finalize_route": "finalize_route"},
)
builder.add_edge("route_tools",    "route_llm")
builder.add_edge("finalize_route", END)

app = builder.compile()


# ── Orchestrator ───────────────────────────────────────────────────────────────

def orchestrate(
    budget: float,
    categories: list[str],
    n_people: int,
    max_shops: int,
    home_address: str,
    transport_mode: str,
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

    print("\n[Agent 1] Shopping Optimizer — building basket...\n")

    result = app.invoke({
        "budget":          budget,
        "categories":      categories,
        "n_people":        n_people,
        "max_shops":       max_shops,
        "home_address":    home_address,
        "transport_mode":  transport_mode,
        "max_dist":        max_distance_km,
        "max_dur":         max_duration_min,
        "ors_key":         ors_api_key,
        "basket":          {},
        "shops_for_route": [],
        "route_messages":  [],
        "route_report":    "",
    })

    shops_for_route = result.get("shops_for_route", [])
    if shops_for_route and ors_api_key:
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
        home_address="Universidad Carlos III de Madrid, Leganés",
        transport_mode="driving-car",
        max_distance_km=12.0,
        max_duration_min=40.0,
        ors_api_key=_load_ors_key(),
    )
