"""Seed demo data so the app opens with something to look at.

Run against a fresh database:  python -m app.seed
"""

from __future__ import annotations

import os
from pathlib import Path

from . import auth, repo
from .db import connect, init_db

PRODUCTS = [
    ("CEM-025", "Cemento gris 25 kg", "saco", 420000, 590000, 20),
    ("FIE-012", "Fierro estriado 12 mm", "barra", 810000, 1090000, 15),
    ("CLV-002", "Clavo corriente 2\"", "kg", 145000, 229000, 40),
    ("PST-001", "Pintura látex blanca 1 gal", "gal", 1250000, 1790000, 8),
    ("TAL-001", "Taladro percutor 650 W", "un", 3850000, 5490000, 5),
    ("SIL-001", "Silicón transparente", "un", 180000, 349000, 30),
]


def main() -> None:
    db_path = os.environ.get("DB_PATH", "data/inventario.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    init_db(conn)

    if conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0:
        auth.create_user(conn, username="admin", password="admin123", role=auth.ROLE_ADMIN)
        auth.create_user(conn, username="vendedor", password="vende123", role=auth.ROLE_SELLER)

    if conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] > 0:
        print("La base ya tiene productos; no se siembra de nuevo.")
        conn.close()
        return

    ids = {}
    for sku, name, unit, cost, price, minimum in PRODUCTS:
        ids[sku] = repo.create_product(conn, sku=sku, name=name, unit=unit,
                                       cost_cents=cost, price_cents=price, min_stock=minimum)

    # Initial purchase, received: gives everything a healthy starting stock.
    order = repo.create_document(conn, kind="orden_compra", party_name="Distribuidora Andes Ltda",
                                 party_tax_id="76.543.210-8", notes="Carga inicial de bodega",
                                 lines=[{"product_id": ids[sku], "description": name, "qty": qty * 3,
                                         "unit_price_cents": cost}
                                        for sku, name, _u, cost, _p, qty in PRODUCTS])
    repo.issue_document(conn, order)
    repo.receive_purchase_order(conn, order)

    # A quote that was converted into a sale, which then moved stock.
    quote = repo.create_document(conn, kind="cotizacion", party_name="Constructora Río Claro",
                                 party_tax_id="77.111.222-3", notes="Obra calle Los Aromos",
                                 lines=[
                                     {"product_id": ids["CEM-025"], "description": "Cemento gris 25 kg",
                                      "qty": 10, "unit_price_cents": 590000},
                                     {"product_id": ids["FIE-012"], "description": "Fierro estriado 12 mm",
                                      "qty": 6, "unit_price_cents": 1090000},
                                 ])
    sale = repo.convert_document(conn, quote, "venta")
    repo.issue_document(conn, sale)

    # A sale straight over the counter.
    counter_sale = repo.create_document(conn, kind="venta", party_name="Cliente mostrador",
                                        lines=[
                                            {"product_id": ids["CLV-002"], "description": "Clavo corriente 2\"",
                                             "qty": 3, "unit_price_cents": 229000},
                                            {"product_id": ids["SIL-001"], "description": "Silicón transparente",
                                             "qty": 2, "unit_price_cents": 349000},
                                        ])
    repo.issue_document(conn, counter_sale)

    # A note of sale, and a credit note for a return.
    note = repo.create_document(conn, kind="nota_venta", party_name="Maestranza Puerto",
                                lines=[{"product_id": ids["TAL-001"], "description": "Taladro percutor 650 W",
                                        "qty": 1, "unit_price_cents": 5490000}])
    repo.issue_document(conn, note)

    credit = repo.convert_document(conn, counter_sale, "nota_credito")
    repo.issue_document(conn, credit)

    # Drop one product to its minimum so the replenishment panel has content.
    repo.record_movement(conn, product_id=ids["PST-001"], qty=-16, kind="salida",
                         note="Consumo interno")

    conn.close()
    print(f"Listo. Datos sembrados en {db_path}")


if __name__ == "__main__":
    main()
