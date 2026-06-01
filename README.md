# Tu IAbuela de Confianza

**Intelligent grocery shopping optimizer for Spanish households.** Finds the cheapest products across real supermarket data, builds an optimized basket, and plans the best route to pick everything up — all from an interactive web interface.

Built as a final project for [AISaturdays](https://www.aisaturdays.com/) Madrid.

---

## How It Works

The app has three main interactions, each with a different level of AI involvement:

### 1. 🍳 Recipe Import (LLM-powered)

Paste any recipe text and the AI extracts a structured ingredient list automatically.

```
User pastes: "Para la tortilla necesitas 6 huevos, 3 patatas medianas,
              media cebolla, aceite de oliva y sal"
       ↓
LLM (Gemini Flash / Ollama) extracts:
  → huevos (6 unidades, categoría: huevos)
  → patatas (3 unidades, categoría: verduras)
  → cebolla (0.5 unidades, categoría: verduras)
  → aceite de oliva (1, categoría: aceites)
  → sal (1, categoría: condimentos)
       ↓
Items are added to the grocery list
```

**AI used:** Gemini 2.0 Flash (free tier) or Ollama local model as fallback.

---

### 2. 🛒 Basket Optimization (deterministic algorithm + optional LLM)

Click "Optimizar cesta" to find the cheapest combination of products across stores.

**Without smart match (default, fast, no AI):**

```
Grocery list: ["leche", "pan", "pollo"]
       ↓
SQL keyword search → finds all products matching each term
       ↓
Greedy optimizer → picks cheapest product per category,
                   consolidating into fewest stores (respects max_shops)
       ↓
Result: optimized basket with items, prices, and store assignments
```

**With smart match enabled (🧠 toggle, uses LLM):**

```
Grocery list: ["leche", "pan", "pollo"]
       ↓
SQL keyword search → gets 30 candidates per category
       ↓
LLM filters: "leche" → keeps "Leche entera 1L"
             (removes "Yogur de leche", "Arroz con leche")
       ↓
If no match: LLM suggests closest substitute with explanation
       ↓
Greedy optimizer runs on filtered products
```

**AI used:** Only when "Búsqueda inteligente" checkbox is enabled. Otherwise pure Python.

---

### 3. 🗺️ Route Optimization (Google Maps API, no LLM)

Click "Calcular ruta óptima" to plan the best circular route: home → stores → home.

```
Browser geolocation → gets user's lat/lng
       ↓
Google Maps Directions API with optimizeWaypoints:true
       ↓
Returns: optimal visit order, total distance, duration, route polyline
       ↓
Rendered on interactive dark-themed Google Map with:
  - Custom markers (hover to see store products)
  - Route polyline with glow effect
  - Transport mode selector (🚗 🚶 🚌 🚴)
  - Distance/duration/cost overlay
```

**AI used:** None. Route optimization is done by Google's server-side TSP solver.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (Next.js + React + Tailwind)                  │
│  - Recipe parser (paste text → extract ingredients)     │
│  - Grocery list builder (manual + from recipes)         │
│  - Google Maps interactive map (dark theme, popups)     │
│  - Transport mode selector                              │
└────────────────────────┬────────────────────────────────┘
                         │ Proxied to :8000
┌────────────────────────▼────────────────────────────────┐
│  Backend (FastAPI + Python)                             │
│  - POST /api/recipe/parse      → LLM ingredient extract│
│  - POST /api/basket/optimize   → greedy optimizer      │
│  - POST /api/route/optimize    → maps API routing      │
│  - GET  /api/stores/nearby     → geo-filtered stores   │
│  - GET  /api/products/search   → product search        │
└────────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   Supabase DB    Google Maps API    LLM Provider
   (PostgreSQL)   (Directions,       (Gemini Flash
    - stores       Geocoding)         or Ollama)
    - products
    - prices
    - categories
```

---

## Swappable Providers

The backend uses an abstraction layer so you can swap providers without code changes:

| Component | Default          | Alternative      | Switch via            |
| --------- | ---------------- | ---------------- | --------------------- |
| Maps      | Google Maps      | OpenRouteService | `MAPS_PROVIDER=ors`   |
| LLM       | Gemini 2.0 Flash | Ollama (local)   | `LLM_PROVIDER=ollama` |

---

## Running the project

### Prerequisites

- Python 3.11+ with [uv](https://docs.astral.sh/uv/getting-started/installation/) installed
- Node.js 18+ with npm
- A Supabase project (or any PostgreSQL instance with the schema applied)

---

### Backend

**1. Install dependencies**

```bash
cd backend
uv sync
```

**2. Configure environment**

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

```env
# PostgreSQL connection string (Supabase or local)
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@YOUR_HOST:5432/postgres

# Maps provider: "google" (full features) or "ors" (free, no transit support)
MAPS_PROVIDER=google
GOOGLE_MAPS_API_KEY=your_google_maps_key
ORS_API_KEY=your_ors_key_as_fallback

# LLM provider: "gemini" (recommended), "openai", or "ollama" (local)
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

# Must match the frontend URL for CORS
FRONTEND_URL=http://localhost:3000
```

**3. Start the server**

```bash
uv run uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

**Using Ollama (local LLM, no API key needed)**

```bash
# Install Ollama from https://ollama.com, then pull the model
ollama pull qwen2.5:7b

# Set in .env:
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=qwen2.5:7b
```

Note: with Ollama, basket optimization with many categories can take 2–4 minutes.

---

### Frontend

**1. Install dependencies**

```bash
cd frontend
npm install
```

**2. Configure environment**

Create `frontend/.env.local`:

```env
# Map rendering: "leaflet" (OpenStreetMap, no key needed) or "google"
NEXT_PUBLIC_MAPS_PROVIDER=leaflet

# Only required when NEXT_PUBLIC_MAPS_PROVIDER=google
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=your_google_maps_key
```

The default `leaflet` option uses OpenStreetMap and requires no API key.

**3. Start the dev server**

```bash
npm run dev
```

The app will be available at `http://localhost:3000`. The frontend proxies API calls to the backend at `http://localhost:8000`.

---

### Required API Keys

| Key | Where to get it | Required |
|---|---|---|
| `DATABASE_URL` | Supabase project settings → Connection string | Always |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) (free tier available) | If `LLM_PROVIDER=gemini` |
| `OPENAI_API_KEY` | [OpenAI Platform](https://platform.openai.com/api-keys) | If `LLM_PROVIDER=openai` |
| `GOOGLE_MAPS_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) | If using Google Maps provider |
| `ORS_API_KEY` | [openrouteservice.org](https://openrouteservice.org/dev/#/signup) (free tier available) | If `MAPS_PROVIDER=ors` |

If using Google Maps, enable these APIs in your Google Cloud project: Maps JavaScript API, Directions API, Geocoding API, Routes API.

---

## Database Schema (Supabase)

| Table             | Purpose                                                  |
| ----------------- | -------------------------------------------------------- |
| `stores`          | Supermarket locations (chain, address, lat/lng, hours)   |
| `products`        | Product catalog (name, barcode, brand, category, store)  |
| `price_snapshots` | Historical prices (price, promo flag, scraped timestamp) |
| `categories`      | Product categories (slug, name)                          |
| `scrape_runs`     | Scraping job metadata                                    |

---

## Legacy CLI Agent

The original `agents_v2.py` still works as a standalone CLI tool. It uses a LangGraph state machine with Ollama to run the full pipeline (basket + route) in the terminal:

```bash
export DATABASE_URL="your_supabase_url"
uv run agents_v2.py
```

This version uses an LLM agent (qwen2.5) for route planning decisions — the web app replaced that with direct API calls for speed and reliability.

---

## Tech Stack

| Layer              | Technology                                               |
| ------------------ | -------------------------------------------------------- |
| Frontend           | Next.js 15, React 19, Tailwind CSS 4, Google Maps JS API |
| Backend            | FastAPI, Python 3.11, psycopg2                           |
| Database           | Supabase (PostgreSQL)                                    |
| LLM                | Gemini 2.0 Flash (cloud) / Ollama + qwen2.5 (local)      |
| Maps & Routing     | Google Maps Directions API / OpenRouteService            |
| Package management | uv (Python), npm (JS)                                    |

---

## Project by

Sam Reskala, Daniel Talavera and Pablo Barrocal — AISaturdays Madrid, 2025
