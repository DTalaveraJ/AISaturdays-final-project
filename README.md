# Tu IAbuela de Confianza

**Intelligent consumption optimization for Spanish households** — scrapes real supermarket prices, stores them in a local database, and provides an interactive route optimizer to plan shopping trips across multiple stores.

Built as a project for [AISaturdays](https://www.aisaturdays.com/) Madrid.

---

## What this project does

1. **Fetches real product data** from Mercadona, Alcampo, and Dia APIs, normalizes prices (including IVA and discounts), and stores everything in a local SQLite database.
2. **Optimizes the grocery basket** using a local LLM agent that selects the cheapest products covering every requested category, within a maximum number of shops.
3. **Plans a circular shopping route** using a second LLM agent that calls OpenRouteService to find the optimal visit order starting and ending at the client's home. If the route exceeds the user's time limit, it suggests the closest and cheapest single-shop alternatives.
4. **Exposes a standalone web optimizer** (`iabuela-route-optimizer.html`) for interactive route planning directly in the browser.

---

## Project structure

```
AISaturdays-final-project/
├── agents.py                      # Two-agent system: shopping optimizer + route optimizer
├── create_catalog_db.py           # Creates iabuela_catalog.db with dummy shop/product data
├── iabuela-route-optimizer.html   # Standalone browser-based route optimizer
├── lA_abuela.py                   # Data pipeline: scrapes supermarket APIs → SQLite
├── ppt.py                         # Generates the project PowerPoint from a template
├── iabuela_mvp.db                 # SQLite database with real Madrid supermarket data
├── iabuela_catalog.db             # SQLite database with dummy catalog (5 shops, 20 products)
├── iabuela_export.json            # JSON export of the product catalog
├── my_apikey.json                 # OpenRouteService API key (read automatically by agents.py)
├── openrouteservice/              # Fork of OpenRouteService (self-hosted routing engine)
└── docs/                          # Presentations and data source references
```

---

## Components

### Multi-agent optimizer (`agents.py`)

Runs locally via [Ollama](https://ollama.com) using `qwen2.5-coder:7b-instruct-q4_K_M`.

```bash
pip install ollama
ollama pull qwen2.5-coder:7b-instruct-q4_K_M
python agents.py
```

**Agent 1 — Shopping Optimizer**

Given a budget, list of food categories, number of people, and maximum number of shops:
- Queries `iabuela_catalog.db` for the cheapest product in each category.
- Coverage is mandatory — all categories are always included even if the total exceeds the budget.
- Consolidates products into the fewest shops possible (up to `max_shops`).
- If the LLM misses any category, a Python safety net fills the gap automatically from the DB.

**Agent 2 — Route Optimizer**

Given the shops selected by Agent 1 and a distance/duration limit:
- Geocodes the client's home address via OpenRouteService.
- Solves the Vehicle Routing Problem (VRP) to find the optimal circular route: home → shops → home.
- If the route exceeds the time or distance limit, drops shops one by one until it fits.
- If even the closest single shop exceeds the limit, suggests two alternatives:
  - **Option A — Closest**: shop with the lowest round-trip travel time.
  - **Option B — Cheapest**: shop with the lowest basket cost.
- Uses the ORS Matrix API for efficient single-call travel-time ranking across all shops.

**Orchestrator**

Wires both agents in sequence. Configurable inputs:

| Parameter | Description |
|-----------|-------------|
| `budget` | Soft spending target in € |
| `categories` | List of food categories to cover (e.g. `["leche", "pan", "aceite"]`) |
| `n_people` | Household size — scales quantities |
| `max_shops` | Maximum number of different shops to visit |
| `home_address` | Client's starting and ending point |
| `transport_mode` | `driving-car`, `cycling-regular`, or `foot-walking` |
| `max_distance_km` | Hard route distance limit |
| `max_duration_min` | Hard route duration limit |

The ORS API key is read automatically from `my_apikey.json`.

### Catalog database (`create_catalog_db.py`)

Creates `iabuela_catalog.db` with two tables and no external API calls:

| Table | Columns |
|-------|---------|
| `shops` | `shop_id`, `name`, `chain`, `address`, `latitude`, `longitude`, `city`, `postal_code` |
| `products` | `product_id`, `name`, `sku`, `price`, `shop_id` |

Seeded with 5 Madrid shops (Mercadona, Alcampo, Dia, Carrefour, Lidl) and 20 common grocery products repeated across all shops with chain-specific price multipliers.

```bash
python create_catalog_db.py
```

### Route Optimizer web app (`iabuela-route-optimizer.html`)

A single-file web app — no build step, no dependencies to install.

- Open it in a browser and enter your [OpenRouteService API key](https://openrouteservice.org/dev/#/login).
- Add supermarket addresses (defaults to three Madrid locations as a demo).
- Choose a transport mode: car, bike, or walking.
- Click **Optimizar Ruta** to geocode the addresses, solve the VRP, and render the optimal route on a Leaflet map.

The app calls the public ORS API by default. To use the local fork instead, change the base URL in the script to `http://localhost:8080/ors`.

### Data pipeline (`lA_abuela.py`)

Scrapes and normalizes product catalogs from real supermarket APIs:

| Supermarket | API endpoint used |
|-------------|------------------|
| Mercadona   | `tienda.mercadona.es/api/categories/` |
| Alcampo     | Compra online product endpoints |
| Dia         | Analytics and product page endpoints |

```bash
python lA_abuela.py
```

Creates/updates `iabuela_mvp.db` with shops, categories, subcategories, and products (price, discount, IVA, weight, origin).

### Self-hosted routing engine (`openrouteservice/`)

This folder is a fork of [GIScience/openrouteservice](https://github.com/GIScience/openrouteservice), a Java/Spring Boot service providing the routing, geocoding, and optimization APIs used by both the web app and the Python agents.

```bash
cd openrouteservice
docker-compose up
```

The service starts on `http://localhost:8080`. You need an OSM extract (`.pbf` file) for the engine to build its routing graph. See [`openrouteservice/README.md`](openrouteservice/README.md) for full setup instructions.

---

## Quick start

**Browser route optimizer (no Python needed):**
1. Get a free API key at https://openrouteservice.org/dev/#/login
2. Open `iabuela-route-optimizer.html` in any modern browser
3. Paste your key, add addresses, click Optimizar Ruta

**Full agent pipeline:**
```bash
# 1. Install dependencies
pip install ollama
ollama pull qwen2.5-coder:7b-instruct-q4_K_M

# 2. Create the catalog database (dummy data, no API needed)
python create_catalog_db.py

# 3. Place your ORS API key in my_apikey.json
#    (a plain JSON string: "your_key_here")

# 4. Run the agents
python agents.py
```

**To use real supermarket data instead of dummy data:**
```bash
python lA_abuela.py   # populates iabuela_mvp.db
# then point DB_PATH in agents.py to iabuela_mvp.db
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| LLM agents | Ollama · qwen2.5-coder:7b-instruct-q4_K_M |
| Data scraping | Python (urllib, sqlite3) |
| Database | SQLite |
| Routing engine | OpenRouteService (Java / Spring Boot) |
| Frontend | Vanilla JS, Leaflet.js |
| Containerization | Docker / docker-compose |

---

## License

The `openrouteservice/` fork is licensed under LGPL — see [`openrouteservice/LICENSE`](openrouteservice/LICENSE) and [`openrouteservice/LICENSE.LESSER`](openrouteservice/LICENSE.LESSER).

The rest of this project was created for educational purposes at AISaturdays Madrid.
