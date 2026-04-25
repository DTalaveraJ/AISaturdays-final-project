"""
create_catalog_db.py
--------------------
Creates iabuela_catalog.db with two tables:
  - shops    : shop_id, name, chain, address, latitude, longitude, city, postal_code
  - products : product_id, name, sku, price, shop_id

20 dummy products are inserted in all 5 shops with slightly different prices per shop.
Run with: python create_catalog_db.py
"""

import sqlite3
import os

DB_PATH = "iabuela_catalog.db"

# ── Seed data ──────────────────────────────────────────────────────────────────

SHOPS = [
    {
        "name": "Mercadona Goya",
        "chain": "Mercadona",
        "address": "Calle de Goya, 47",
        "latitude": 40.4256,
        "longitude": -3.6803,
        "city": "Madrid",
        "postal_code": "28001",
    },
    {
        "name": "Alcampo Paseo Imperial",
        "chain": "Alcampo",
        "address": "Paseo Imperial, 40",
        "latitude": 40.4060,
        "longitude": -3.7180,
        "city": "Madrid",
        "postal_code": "28005",
    },
    {
        "name": "Dia Lavapiés",
        "chain": "Dia",
        "address": "Calle de Embajadores, 35",
        "latitude": 40.4090,
        "longitude": -3.7033,
        "city": "Madrid",
        "postal_code": "28012",
    },
    {
        "name": "Carrefour Princesa",
        "chain": "Carrefour",
        "address": "Calle de la Princesa, 56",
        "latitude": 40.4318,
        "longitude": -3.7143,
        "city": "Madrid",
        "postal_code": "28008",
    },
    {
        "name": "Lidl Vallecas",
        "chain": "Lidl",
        "address": "Avenida de la Albufera, 100",
        "latitude": 40.3876,
        "longitude": -3.6511,
        "city": "Madrid",
        "postal_code": "28038",
    },
]

# (sku, name, base_price)
PRODUCTS = [
    ("P001", "Leche entera 1L",               0.99),
    ("P002", "Pan de molde integral 500g",     1.45),
    ("P003", "Aceite de oliva virgen 1L",      4.99),
    ("P004", "Arroz redondo 1kg",              0.89),
    ("P005", "Pasta espagueti 500g",           0.75),
    ("P006", "Tomate frito 400g",              0.85),
    ("P007", "Atún en aceite (pack 3 latas)",  2.10),
    ("P008", "Huevos camperos L (docena)",     2.75),
    ("P009", "Yogur natural (pack 4)",         1.20),
    ("P010", "Mantequilla 250g",               1.65),
    ("P011", "Zumo de naranja 1L",             1.35),
    ("P012", "Agua mineral 6x1.5L",            2.49),
    ("P013", "Detergente líquido 30 lavados",  4.20),
    ("P014", "Papel higiénico 12 rollos",      3.99),
    ("P015", "Café molido 250g",               2.89),
    ("P016", "Lentejas cocidas 400g",          0.69),
    ("P017", "Pechuga de pollo 1kg",           5.50),
    ("P018", "Queso manchego curado 200g",     3.20),
    ("P019", "Chocolate negro 72% 100g",       1.10),
    ("P020", "Cerveza rubia 6x330ml",          3.75),
]

# Price variation per chain: a multiplier applied to the base price
PRICE_FACTORS = {
    "Mercadona": 1.00,
    "Alcampo":   1.03,
    "Dia":       0.95,
    "Carrefour": 1.07,
    "Lidl":      0.92,
}

# ── Schema ─────────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS shops (
    shop_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    chain       TEXT NOT NULL,
    address     TEXT,
    latitude    REAL,
    longitude   REAL,
    city        TEXT,
    postal_code TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    sku         TEXT,
    price       REAL NOT NULL,
    shop_id     INTEGER NOT NULL REFERENCES shops(shop_id)
);

CREATE INDEX IF NOT EXISTS idx_products_shop  ON products(shop_id);
CREATE INDEX IF NOT EXISTS idx_products_price ON products(price);
"""

# ── Build database ─────────────────────────────────────────────────────────────

def build(db_path: str = DB_PATH):
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.executescript(DDL)
    conn.commit()
    print(f"Database created: {db_path}\n")

    # Insert shops
    shop_ids = {}
    for shop in SHOPS:
        cur = conn.execute(
            """INSERT INTO shops (name, chain, address, latitude, longitude, city, postal_code)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (shop["name"], shop["chain"], shop["address"],
             shop["latitude"], shop["longitude"],
             shop["city"], shop["postal_code"]),
        )
        shop_ids[shop["chain"]] = cur.lastrowid
    conn.commit()
    print(f"Shops inserted: {len(SHOPS)}")

    # Insert all 20 products in every shop with chain-specific prices
    total = 0
    for shop in SHOPS:
        chain = shop["chain"]
        shop_id = shop_ids[chain]
        factor = PRICE_FACTORS[chain]
        rows = [
            (name, sku, round(base * factor, 2), shop_id)
            for sku, name, base in PRODUCTS
        ]
        conn.executemany(
            "INSERT INTO products (name, sku, price, shop_id) VALUES (?, ?, ?, ?)",
            rows,
        )
        total += len(rows)

    conn.commit()
    conn.close()
    print(f"Products inserted: {total}  ({len(PRODUCTS)} products × {len(SHOPS)} shops)\n")
    print(f"Done → {db_path}")


# ── Cross-shop price comparison ────────────────────────────────────────────────

def query_cross_shop(db_path: str = DB_PATH):
    """Print a side-by-side price table for every product across all shops."""
    conn = sqlite3.connect(db_path)

    shops = conn.execute("SELECT shop_id, chain FROM shops ORDER BY shop_id").fetchall()
    chain_ids = [(shop_id, chain) for shop_id, chain in shops]
    chains = [chain for _, chain in chain_ids]

    rows = conn.execute(
        """SELECT p.sku, p.name, s.chain, p.price
           FROM products p
           JOIN shops s ON p.shop_id = s.shop_id
           ORDER BY p.sku, s.chain"""
    ).fetchall()
    conn.close()

    # Build {sku: {chain: price}}
    from collections import defaultdict
    table: dict[str, dict] = defaultdict(dict)
    names: dict[str, str] = {}
    for sku, name, chain, price in rows:
        table[sku][chain] = price
        names[sku] = name

    col = 12
    header = f"  {'SKU':<6}  {'Product':<35}" + "".join(f"{c:<{col}}" for c in chains)
    sep = "  " + "─" * (6 + 2 + 35 + col * len(chains))

    print(f"\n{'─'*80}")
    print("  Cross-shop price comparison")
    print(f"{'─'*80}")
    print(header)
    print(sep)

    for sku in sorted(table):
        prices = table[sku]
        cheapest = min(prices, key=prices.get)
        price_cols = ""
        for chain in chains:
            p = prices.get(chain)
            cell = f"{p:.2f}€" if p is not None else "—"
            marker = "*" if chain == cheapest else " "
            price_cols += f"{marker}{cell:<{col-1}}"
        print(f"  {sku:<6}  {names[sku]:<35}{price_cols}")

    print(f"\n  * = cheapest for that product\n")


if __name__ == "__main__":
    build()
    query_cross_shop()
