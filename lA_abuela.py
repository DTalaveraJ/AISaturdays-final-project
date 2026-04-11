# FINAL PROJECT MVP - DATOS REALES

"""
IAbuela - Pipeline de datos reales
=====================================
Conecta con las APIs públicas de supermercados españoles:
  - Mercadona: https://tienda.mercadona.es/api/categories/
  - Alcampo:   https://www.compraonline.alcampo.es/api/webproductpagews/v5/product-pages
  - Dia:       https://www.dia.es/api/v2/home-insight/initial_analytics
"""

import sqlite3
import json
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

# ──────────────────────────────────────────────
# 1. SCHEMA DE BASE DE DATOS
# ──────────────────────────────────────────────

DB_PATH = "iabuela_mvp.db"

DDL = """
-- Tabla de tiendas / supermercados
CREATE TABLE IF NOT EXISTS shop (
    shop_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_name     TEXT    NOT NULL,
    chain         TEXT    NOT NULL,
    address       TEXT,
    latitude      REAL,
    longitude     REAL,
    opening_time  TEXT,
    closing_time  TEXT,
    postal_code   TEXT,
    city          TEXT
);

-- Tabla de categorías
CREATE TABLE IF NOT EXISTS category (
    category_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name   TEXT NOT NULL UNIQUE
);

-- Tabla de subcategorías
CREATE TABLE IF NOT EXISTS subcategory (
    subcategory_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    subcategory_name TEXT NOT NULL UNIQUE
);

-- Tabla de productos
CREATE TABLE IF NOT EXISTS product (
    product_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name        TEXT    NOT NULL,
    brand               TEXT,
    sku                 TEXT,
    product_description TEXT,
    price               REAL    NOT NULL,
    price_per_unit      REAL,
    price_per_kg        REAL,
    discount            REAL    DEFAULT 0,
    iva                 REAL    DEFAULT 10,
    weight_g            REAL,
    origin              TEXT,
    stock               INTEGER,
    last_update         TEXT    NOT NULL,
    shop_id             INTEGER NOT NULL REFERENCES shop(shop_id),
    category_id         INTEGER REFERENCES category(category_id),
    subcategory_id      INTEGER REFERENCES subcategory(subcategory_id)
);

-- Tabla de usuarios
CREATE TABLE IF NOT EXISTS user (
    user_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name  TEXT NOT NULL,
    email      TEXT UNIQUE,
    postal_code TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_product_shop     ON product(shop_id);
CREATE INDEX IF NOT EXISTS idx_product_category ON product(category_id);
CREATE INDEX IF NOT EXISTS idx_product_sku      ON product(sku);
CREATE INDEX IF NOT EXISTS idx_product_name     ON product(product_name);
"""

# ──────────────────────────────────────────────
# 2. FETCHERS DE APIS REALES
# ──────────────────────────────────────────────

# Tiendas representativas (ubicaciones reales de cada cadena en Madrid)
SHOPS = [
    {
        "shop_name": "Mercadona Goya",
        "chain": "Mercadona",
        "address": "Calle de Goya, 47",
        "latitude": 40.4256, "longitude": -3.6803,
        "opening_time": "09:00", "closing_time": "21:30",
        "postal_code": "28001", "city": "Madrid",
    },
    {
        "shop_name": "Alcampo Paseo Imperial",
        "chain": "Alcampo",
        "address": "Paseo Imperial, 40",
        "latitude": 40.4060, "longitude": -3.7180,
        "opening_time": "09:00", "closing_time": "22:00",
        "postal_code": "28005", "city": "Madrid",
    },
    {
        "shop_name": "Dia Lavapiés",
        "chain": "Dia",
        "address": "Calle de Embajadores, 35",
        "latitude": 40.4090, "longitude": -3.7033,
        "opening_time": "09:00", "closing_time": "21:00",
        "postal_code": "28012", "city": "Madrid",
    },
]

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _get_json(url: str, extra_headers: dict = None, timeout: int = 15) -> dict:
    """HTTP GET → JSON. Lanza excepción si falla."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; IAbuela/1.0)",
        "Accept": "application/json",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=_SSL_CTX, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_mercadona(max_subcategories: int = None) -> list[dict]:
    """
    Descarga productos reales de Mercadona.
    1. Obtiene la lista de todas las categorías y subcategorías.
    2. Para cada subcategoría, descarga los productos.
    Devuelve lista normalizada de dicts.
    """
    print("  Mercadona: obteniendo categorías...")
    cats_data = _get_json("https://tienda.mercadona.es/api/categories/")

    subcats = []
    for parent in cats_data.get("results", []):
        for sub in parent.get("categories", []):
            subcats.append((parent["name"], sub["id"], sub["name"]))

    if max_subcategories:
        subcats = subcats[:max_subcategories]

    print(f"  Mercadona: {len(subcats)} subcategorías → descargando productos...")

    products = []
    for parent_name, cat_id, cat_name in subcats:
        try:
            data = _get_json(f"https://tienda.mercadona.es/api/categories/{cat_id}/")
            for subcat in data.get("categories", []):
                for p in subcat.get("products", []):
                    pi = p.get("price_instructions", {})
                    unit_price = pi.get("unit_price")
                    if not unit_price:
                        continue

                    # Peso
                    unit_size = pi.get("unit_size")
                    size_fmt = (pi.get("size_format") or "").lower()
                    weight_g = None
                    if unit_size:
                        if size_fmt == "kg":
                            weight_g = float(unit_size) * 1000
                        elif size_fmt == "g":
                            weight_g = float(unit_size)
                        elif size_fmt == "l":
                            weight_g = float(unit_size) * 1000  # ml equivalente
                        elif size_fmt == "ml":
                            weight_g = float(unit_size)

                    # Precio de referencia (por kg o L)
                    ref_price = pi.get("reference_price")
                    price_per_kg = float(ref_price) if ref_price else None

                    # Descuento
                    prev = pi.get("previous_unit_price")
                    discount = 0.0
                    if prev:
                        p_prev = float(prev)
                        p_curr = float(unit_price)
                        if p_prev > p_curr:
                            discount = round((p_prev - p_curr) / p_prev * 100)

                    # IVA
                    tax = pi.get("tax_percentage") or pi.get("iva") or 10
                    try:
                        iva = float(tax)
                    except (TypeError, ValueError):
                        iva = 10.0

                    products.append({
                        "product_name": p.get("display_name", ""),
                        "brand": None,
                        "sku": str(p.get("id", "")),
                        "price": float(unit_price),
                        "price_per_unit": float(unit_price),
                        "price_per_kg": price_per_kg,
                        "discount": discount,
                        "iva": iva,
                        "weight_g": weight_g,
                        "origin": None,
                        "stock": None,
                        "category": parent_name,
                        "subcategory": cat_name,
                    })
            time.sleep(0.05)
        except Exception as e:
            print(f"    ⚠ Categoría {cat_id} ({cat_name}): {e}")

    print(f"  Mercadona: ✅ {len(products)} productos")
    return products


def fetch_alcampo(max_pages: int = 10) -> list[dict]:
    """
    Descarga productos reales de Alcampo (páginas de oferta).
    """
    print(f"  Alcampo: descargando hasta {max_pages} páginas...")
    products = []

    for page in range(max_pages):
        try:
            url = (
                "https://www.compraonline.alcampo.es/api/webproductpagews/v5/product-pages"
                f"?page={page}&size=30"
            )
            data = _get_json(url)
            groups = data.get("productGroups", [])
            if not groups:
                break

            page_count = 0
            for group in groups:
                for item in group.get("products", []):
                    p = item.get("product", item)
                    price_raw = p.get("price", {}).get("amount")
                    if not price_raw:
                        continue
                    price = float(price_raw)

                    # Precio por unidad de referencia (L, kg)
                    up_info = p.get("unitPrice") or {}
                    up_amount = (up_info.get("price") or {}).get("amount")
                    price_per_kg = float(up_amount) if up_amount else None

                    # Peso desde packSizeDescription, ej: "9000ml", "1.5kg", "6x1.5L"
                    pack = (p.get("packSizeDescription") or "").lower().strip()
                    weight_g = None
                    try:
                        if pack.endswith("kg"):
                            weight_g = float(pack[:-2]) * 1000
                        elif pack.endswith("g"):
                            weight_g = float(pack[:-1])
                        elif pack.endswith("ml"):
                            weight_g = float(pack[:-2])
                        elif pack.endswith("l"):
                            weight_g = float(pack[:-1]) * 1000
                    except ValueError:
                        pass

                    discount = 10.0 if p.get("promotions") else 0.0
                    stock = 1 if p.get("available") else 0

                    products.append({
                        "product_name": p.get("name", ""),
                        "brand": p.get("brand"),
                        "sku": p.get("retailerProductId"),
                        "price": price,
                        "price_per_unit": price,
                        "price_per_kg": price_per_kg,
                        "discount": discount,
                        "iva": 10.0,
                        "weight_g": weight_g,
                        "origin": None,
                        "stock": stock,
                        "category": "general",
                        "subcategory": group.get("type", "food"),
                    })
                    page_count += 1

            if page_count == 0:
                break
            time.sleep(0.05)
        except Exception as e:
            print(f"    ⚠ Página {page}: {e}")
            break

    print(f"  Alcampo: ✅ {len(products)} productos")
    return products


def fetch_dia() -> list[dict]:
    """
    Descarga productos reales de Dia desde el endpoint de analytics.
    Extrae todos los productos de todos los carruseles (deduplica por ID).
    """
    print("  Dia: obteniendo productos...")
    data = _get_json("https://www.dia.es/api/v2/home-insight/initial_analytics")

    seen = set()
    products = []

    for carousel in data.get("carousel_analytics", {}).values():
        for item_id, item in carousel.items():
            if item_id in seen:
                continue
            seen.add(item_id)

            price = item.get("price")
            if not price:
                continue

            brand_raw = item.get("item_brand", "") or ""
            brand = brand_raw.title() if brand_raw.lower() != "sin marca" else None

            products.append({
                "product_name": (item.get("item_name") or "").title(),
                "brand": brand,
                "sku": item.get("item_id"),
                "price": float(price),
                "price_per_unit": float(price),
                "price_per_kg": None,
                "discount": 0.0,
                "iva": 10.0,
                "weight_g": None,
                "origin": None,
                "stock": 1 if item.get("stock_availability") else 0,
                "category": item.get("item_category", "general"),
                "subcategory": item.get("item_category2", "food"),
            })

    print(f"  Dia: ✅ {len(products)} productos")
    return products


# Mapa cadena → función fetcheadora
FETCHERS = {
    "Mercadona": fetch_mercadona,
    "Alcampo": fetch_alcampo,
    "Dia": fetch_dia,
}

# ──────────────────────────────────────────────
# 3. PIPELINE: INGESTA → DB
# ──────────────────────────────────────────────

def init_db(conn: sqlite3.Connection):
    conn.executescript(DDL)
    conn.commit()
    print("✅ Base de datos inicializada")


def upsert_taxonomy(conn: sqlite3.Connection, table: str, name_col: str, id_col: str, value: str) -> Optional[int]:
    """Inserta si no existe y devuelve el ID."""
    conn.execute(f"INSERT OR IGNORE INTO {table} ({name_col}) VALUES (?)", (value,))
    row = conn.execute(f"SELECT {id_col} FROM {table} WHERE {name_col} = ?", (value,)).fetchone()
    return row[0] if row else None


def ingest_shops(conn: sqlite3.Connection) -> dict:
    shop_ids = {}
    for shop in SHOPS:
        conn.execute(
            """INSERT OR IGNORE INTO shop
               (shop_name, chain, address, latitude, longitude,
                opening_time, closing_time, postal_code, city)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                shop["shop_name"], shop["chain"], shop["address"],
                shop["latitude"], shop["longitude"],
                shop["opening_time"], shop["closing_time"],
                shop["postal_code"], shop["city"],
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT shop_id FROM shop WHERE shop_name = ?", (shop["shop_name"],)
        ).fetchone()
        shop_ids[shop["shop_name"]] = (row[0], shop["chain"])

    print(f"✅ {len(SHOPS)} tiendas insertadas")
    return shop_ids


def ingest_products(conn: sqlite3.Connection, shop_ids: dict):
    """
    Para cada tienda llama a la API real de su cadena e inserta los productos.
    """
    now = datetime.now(timezone.utc).isoformat()
    total = 0

    # Precarga fetchers por cadena (una sola llamada de API por cadena)
    chain_products: dict[str, list] = {}

    for _, (shop_id, chain) in shop_ids.items():
        if chain not in chain_products:
            fetcher = FETCHERS.get(chain)
            if fetcher:
                print(f"\n→ Descargando datos de {chain}...")
                try:
                    chain_products[chain] = fetcher()
                except Exception as e:
                    print(f"  ⚠ Error al obtener datos de {chain}: {e}")
                    chain_products[chain] = []
            else:
                chain_products[chain] = []

        products = chain_products[chain]

        for p in products:
            cat_id = upsert_taxonomy(conn, "category", "category_name", "category_id", p["category"])
            sub_id = upsert_taxonomy(conn, "subcategory", "subcategory_name", "subcategory_id", p["subcategory"])

            conn.execute(
                """INSERT INTO product
                   (product_name, brand, sku, product_description,
                    price, price_per_unit, price_per_kg, discount,
                    iva, weight_g, origin, stock, last_update,
                    shop_id, category_id, subcategory_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    p["product_name"], p["brand"], p["sku"], None,
                    p["price"], p["price_per_unit"], p["price_per_kg"], p["discount"],
                    p["iva"], p["weight_g"], p["origin"], p["stock"], now,
                    shop_id, cat_id, sub_id,
                ),
            )
            total += 1

        conn.commit()

    print(f"\n✅ {total} registros de productos insertados")


# ──────────────────────────────────────────────
# 4. CONSULTAS DE DEMOSTRACIÓN
# ──────────────────────────────────────────────

def query_price_comparison(conn: sqlite3.Connection, product_keyword: str):
    print(f"\n{'─'*60}")
    print(f"  🔍 Comparativa de precios: '{product_keyword}'")
    print(f"{'─'*60}")

    rows = conn.execute(
        """SELECT p.product_name, s.chain, s.shop_name,
                  p.price, p.price_per_kg, p.discount, p.stock, p.last_update
           FROM product p
           JOIN shop s ON p.shop_id = s.shop_id
           WHERE LOWER(p.product_name) LIKE ?
           ORDER BY p.price ASC""",
        (f"%{product_keyword.lower()}%",),
    ).fetchall()

    if not rows:
        print("  Sin resultados.")
        return

    cheapest = rows[0]
    for r in rows[:10]:
        tag = " ← más barato" if r == cheapest else ""
        disc = f" (-{r[5]:.0f}%)" if r[5] and r[5] > 0 else ""
        stock_str = f"stock: {r[6]}" if r[6] is not None else "stock: -"
        print(f"  {r[0][:30]:<30} {r[1]:<12} {r[3]:>6.2f}€{disc:<8}  {stock_str:<14}{tag}")


def query_cheapest_basket(conn: sqlite3.Connection, items: list):
    print(f"\n{'─'*60}")
    print("  🛒 Cesta óptima multitienda (precio mínimo por producto)")
    print(f"{'─'*60}")

    results = []
    for item in items:
        row = conn.execute(
            """SELECT p.product_name, s.chain, s.shop_name, p.price
               FROM product p
               JOIN shop s ON p.shop_id = s.shop_id
               WHERE LOWER(p.product_name) LIKE ?
                 AND (p.stock IS NULL OR p.stock > 0)
               ORDER BY p.price ASC LIMIT 1""",
            (f"%{item.lower()}%",),
        ).fetchone()
        if row:
            results.append(row)
            print(f"  {row[0][:35]:<35} → {row[2]:<28} {row[3]:.2f}€")
        else:
            print(f"  {item:<35} → No encontrado")

    if results:
        total = sum(r[3] for r in results)
        print(f"\n  Total cesta mínima: {total:.2f}€")


def query_category_summary(conn: sqlite3.Connection):
    print(f"\n{'─'*60}")
    print("  📊 Precio medio por categoría y cadena")
    print(f"{'─'*60}")

    rows = conn.execute(
        """SELECT c.category_name, s.chain,
                  ROUND(AVG(p.price), 2) AS avg_price,
                  COUNT(p.product_id) AS num_products
           FROM product p
           JOIN shop s     ON p.shop_id     = s.shop_id
           JOIN category c ON p.category_id = c.category_id
           GROUP BY c.category_name, s.chain
           ORDER BY num_products DESC, c.category_name"""
    ).fetchall()

    current_cat = None
    for r in rows[:40]:
        if r[0] != current_cat:
            current_cat = r[0]
            print(f"\n  [{current_cat.upper()}]")
        print(f"    {r[1]:<14} avg: {r[2]:>6.2f}€   ({r[3]} productos)")


def export_to_json(conn: sqlite3.Connection, filepath: str = "iabuela_export.json"):
    rows = conn.execute(
        """SELECT p.product_name, p.brand, p.sku,
                  p.price, p.price_per_kg, p.discount, p.iva,
                  p.weight_g, p.origin, p.stock, p.last_update,
                  s.chain, s.shop_name, s.address, s.latitude, s.longitude,
                  s.postal_code, s.city,
                  c.category_name, sc.subcategory_name
           FROM product p
           JOIN shop s          ON p.shop_id       = s.shop_id
           LEFT JOIN category c   ON p.category_id   = c.category_id
           LEFT JOIN subcategory sc ON p.subcategory_id = sc.subcategory_id"""
    ).fetchall()

    columns = [
        "product_name", "brand", "sku",
        "price", "price_per_kg", "discount", "iva",
        "weight_g", "origin", "stock", "last_update",
        "chain", "shop_name", "address", "latitude", "longitude",
        "postal_code", "city", "category", "subcategory"
    ]
    data = [dict(zip(columns, r)) for r in rows]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Exportados {len(data)} registros → {filepath}")


# ──────────────────────────────────────────────
# 5. MAIN
# ──────────────────────────────────────────────

def main():
    import os
    print("\n🛒 IAbuela — Pipeline de datos reales")
    print("=" * 60)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)

    init_db(conn)
    shop_ids = ingest_shops(conn)
    ingest_products(conn, shop_ids)

    # Consultas de demostración
    query_price_comparison(conn, "agua")
    query_price_comparison(conn, "leche")
    query_price_comparison(conn, "pollo")

    query_cheapest_basket(conn, [
        "agua",
        "leche",
        "pollo",
        "merluza",
        "lentejas",
        "tomate",
    ])

    query_category_summary(conn)
    export_to_json(conn, "iabuela_export.json")

    conn.close()
    print("\n✅ Pipeline completado. Base de datos: iabuela_mvp.db")


if __name__ == "__main__":
    main()
