# IAbuela — Project Structure

## Overview

```
AISaturdays-final-project/
├── backend/                    # FastAPI Python backend
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── config.py          # Settings from env vars
│   │   ├── db.py              # Supabase PostgreSQL connection
│   │   ├── routers/
│   │   │   ├── stores.py      # GET /api/stores/nearby, /chains
│   │   │   ├── products.py    # GET /api/products/search, /categories
│   │   │   ├── basket.py      # POST /api/basket/optimize
│   │   │   ├── route.py       # POST /api/route/optimize
│   │   │   └── recipe.py      # POST /api/recipe/parse
│   │   └── services/
│   │       ├── maps.py        # Abstract maps interface
│   │       ├── maps_google.py # Google Maps implementation
│   │       ├── maps_ors.py    # OpenRouteService fallback
│   │       ├── llm.py         # Abstract LLM interface
│   │       ├── llm_gemini.py  # Gemini Flash implementation
│   │       ├── llm_ollama.py  # Ollama local fallback
│   │       └── factory.py     # Provider factory (reads config)
│   ├── pyproject.toml
│   └── .env.example
├── frontend/                   # Next.js React frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx       # Main page with all components
│   │   │   └── globals.css
│   │   └── components/
│   │       ├── RecipeParser.tsx   # Paste recipe → LLM extracts ingredients
│   │       ├── GroceryList.tsx    # Manual item entry + optimize button
│   │       ├── BasketResult.tsx   # Shows optimized basket + route button
│   │       └── MapView.tsx        # Google Maps with route visualization
│   ├── package.json
│   ├── next.config.ts         # Proxies /api/* to FastAPI backend
│   └── .env.local.example
├── agents_v2.py               # Original CLI agent (still works standalone)
└── create_catalog_db.py       # Legacy SQLite seeder (no longer needed)
```

## Running Locally

### Backend (FastAPI)

```bash
cd backend
cp .env.example .env           # Fill in your keys
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

### Frontend (Next.js)

```bash
cd frontend
cp .env.local.example .env.local   # Add Google Maps key
npm install
npm run dev                         # http://localhost:3000
```

The frontend proxies all `/api/*` requests to the backend at `:8000`.

## Swapping Providers

### Maps: Google → ORS

In `backend/.env`, change:

```
MAPS_PROVIDER=ors
ORS_API_KEY=your_key
```

### LLM: Gemini → Ollama

In `backend/.env`, change:

```
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b
```

Make sure Ollama is running locally.

## API Endpoints

| Method | Path                                    | Description                     |
| ------ | --------------------------------------- | ------------------------------- |
| GET    | /api/stores/nearby?lat=&lng=&radius_km= | Find stores near location       |
| GET    | /api/stores/chains                      | List all chains                 |
| GET    | /api/products/search?q=                 | Search products by name         |
| GET    | /api/products/categories                | List categories                 |
| POST   | /api/basket/optimize                    | Optimize grocery basket         |
| POST   | /api/route/optimize                     | Compute optimal route           |
| POST   | /api/recipe/parse                       | Extract ingredients from recipe |
| GET    | /api/health                             | Health check                    |
