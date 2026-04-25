# Tu IAbuela de Confianza

**Intelligent consumption optimization for Spanish households** — scrapes real supermarket prices, stores them in a local database, and provides an interactive route optimizer to plan shopping trips across multiple stores.

Built as a project for [AISaturdays](https://www.aisaturdays.com/) Madrid.

---

## What this project does

1. **Fetches real product data** from Mercadona, Alcampo, and Dia APIs, normalizes prices (including IVA and discounts), and stores everything in a local SQLite database.
2. **Exposes a route optimizer** web app that calls OpenRouteService to find the optimal order to visit multiple supermarkets, showing distance, time, and turn-by-turn directions on an interactive map.
3. The OpenRouteService instance used by the optimizer can be run locally via Docker using the fork included in this repo (`openrouteservice/`), or you can use the public ORS free-tier API key.

---

## Project structure

```
AISaturdays-final-project/
├── iabuela-route-optimizer.html   # Standalone route optimizer web app
├── lA_abuela.py                   # Data pipeline: scrapes supermarket APIs → SQLite
├── ppt.py                         # Generates the project PowerPoint from a template
├── iabuela_mvp.db                 # SQLite database with Madrid supermarket data
├── iabuela_export.json            # JSON export of the product catalog
├── openrouteservice/              # Fork of OpenRouteService (self-hosted routing engine)
└── docs/                          # Presentations and data source references
```

---

## Components

### Route Optimizer (`iabuela-route-optimizer.html`)

A single-file web app — no build step, no dependencies to install.

- Open it in a browser and enter your [OpenRouteService API key](https://openrouteservice.org/dev/#/login).
- Add supermarket addresses (defaults to three Madrid locations as a demo).
- Choose a transport mode: car, bike, or walking.
- Click **Optimizar Ruta** to geocode the addresses, solve the Vehicle Routing Problem, and render the optimal route on a Leaflet map.

The app calls the public ORS API by default. To use the local fork instead, change the base URL in the script to `http://localhost:8080/ors`.

### Data pipeline (`lA_abuela.py`)

Scrapes and normalizes product catalogs:

| Supermarket | API endpoint used |
|-------------|------------------|
| Mercadona   | `tienda.mercadona.es/api/categories/` |
| Alcampo     | Compra online product endpoints |
| Dia         | Analytics and product page endpoints |

Run it to refresh the local database:

```bash
python lA_abuela.py
```

The script creates/updates `iabuela_mvp.db` with tables for shops, categories, subcategories, and products (including price, discount, IVA, weight, and origin).

### Self-hosted routing engine (`openrouteservice/`)

This folder is a fork of [GIScience/openrouteservice](https://github.com/GIScience/openrouteservice), a Java/Spring Boot service that provides the routing, geocoding, and optimization APIs consumed by the HTML frontend.

**Run it locally with Docker:**

```bash
cd openrouteservice
docker-compose up
```

The service starts on `http://localhost:8080`. Check health at `http://localhost:8080/ors/v2/health`.

You need an OSM extract (`.pbf` file) placed in the configured data directory for the engine to build its routing graph. See [`openrouteservice/README.md`](openrouteservice/README.md) for full setup instructions.

---

## Quick start

**To use the route optimizer with the public ORS API:**

1. Get a free API key at https://openrouteservice.org/dev/#/login
2. Open `iabuela-route-optimizer.html` in any modern browser
3. Paste your API key, add addresses, and click Optimizar Ruta

**To run everything locally:**

```bash
# 1. Start the routing engine
cd openrouteservice && docker-compose up -d

# 2. Populate the product database
cd .. && python lA_abuela.py

# 3. Open the frontend (change the API base URL to localhost:8080 if desired)
open iabuela-route-optimizer.html
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Data scraping | Python (requests, sqlite3) |
| Database | SQLite |
| Routing engine | Java / Spring Boot (OpenRouteService) |
| Frontend | Vanilla JS, Leaflet.js |
| Containerization | Docker / docker-compose |

---

## License

The `openrouteservice/` fork is licensed under LGPL — see [`openrouteservice/LICENSE`](openrouteservice/LICENSE) and [`openrouteservice/LICENSE.LESSER`](openrouteservice/LICENSE.LESSER).

The rest of this project was created for educational purposes at AISaturdays Madrid.
