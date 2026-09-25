"""Domain operations over the SQLite schema.

Stock is derived from an append-only ledger (`stock_movements`). Issuing a sale
writes a negative movement; receiving a purchase order writes a positive one.
Nothing ever overwrites a quantity, so the history is auditable.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import Any, Iterable

from .money import Money, split_iva

KIND_PREFIX = {
    "cotizacion": "COT",
    "nota_venta": "NV",
    "venta": "VTA",
    "orden_compra": "OC",
    "nota_credito": "NC",
}

# Which stock movement a document applies when issued. Kinds absent here have no
# stock effect on their own (a quote is not a sale, an order is not a receipt).
ISSUE_EFFECT = {
    "venta": ("salida", -1),
    "nota_credito": ("entrada", 1),
}


class DomainError(Exception):
    """Raised for invalid operations the caller should surface to the user."""


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #

def create_product(conn: sqlite3.Connection, *, sku: str, name: str, unit: str = "un",
                   cost_cents: int = 0, price_cents: int = 0, min_stock: int = 0) -> int:
    sku = sku.strip()
    if not sku:
        raise DomainError("El SKU es obligatorio.")
    if not name.strip():
        raise DomainError("El nombre es obligatorio.")
    try:
        cur = conn.execute(
            """INSERT INTO products (sku, name, unit, cost_cents, price_cents, min_stock)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sku, name.strip(), unit, cost_cents, price_cents, min_stock),
        )
    except sqlite3.IntegrityError as exc:
        raise DomainError(f"El SKU {sku} ya existe.") from exc
    conn.commit()
    return int(cur.lastrowid)


def update_product(conn: sqlite3.Connection, product_id: int, **fields: Any) -> None:
    allowed = {"sku", "name", "unit", "cost_cents", "price_cents", "min_stock", "active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    assignments = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE products SET {assignments} WHERE id = ?", (*updates.values(), product_id))
    conn.commit()


def stock_level(conn: sqlite3.Connection, product_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(qty), 0) AS qty FROM stock_movements WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    return int(row["qty"])


def list_products(conn: sqlite3.Connection, *, only_active: bool = True) -> list[dict[str, Any]]:
    where = "WHERE p.active = 1" if only_active else ""
    rows = conn.execute(
        f"""SELECT p.*, COALESCE(s.qty, 0) AS stock
            FROM products p
            LEFT JOIN (
                SELECT product_id, SUM(qty) AS qty FROM stock_movements GROUP BY product_id
            ) s ON s.product_id = p.id
            {where}
            ORDER BY p.name COLLATE NOCASE"""
    ).fetchall()
    return [dict(r) for r in rows]


def low_stock(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [p for p in list_products(conn) if p["stock"] <= p["min_stock"]]


def record_movement(conn: sqlite3.Connection, *, product_id: int, qty: int, kind: str,
                    ref_type: str | None = None, ref_id: int | None = None,
                    note: str = "", commit: bool = True) -> None:
    if kind not in {"entrada", "salida", "ajuste"}:
        raise DomainError(f"Tipo de movimiento invalido: {kind}")
    conn.execute(
        """INSERT INTO stock_movements (product_id, qty, kind, ref_type, ref_id, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (product_id, qty, kind, ref_type, ref_id, note),
    )
    if commit:
        conn.commit()


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #

def _next_number(conn: sqlite3.Connection, kind: str) -> str:
    row = conn.execute("SELECT value FROM counters WHERE kind = ?", (kind,)).fetchone()
    value = (int(row["value"]) + 1) if row else 1
    if row:
        conn.execute("UPDATE counters SET value = ? WHERE kind = ?", (value, kind))
    else:
        conn.execute("INSERT INTO counters (kind, value) VALUES (?, ?)", (kind, value))
    return f"{KIND_PREFIX[kind]}-{value:05d}"


def _validate_lines(lines: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for line in lines:
        qty = int(line.get("qty", 0))
        if qty <= 0:
            raise DomainError("Cada linea necesita una cantidad mayor que cero.")
        unit_price = int(line.get("unit_price_cents", 0))
        if unit_price < 0:
            raise DomainError("El precio no puede ser negativo.")
        cleaned.append({
            "product_id": line.get("product_id"),
            "description": line.get("description", ""),
            "qty": qty,
            "unit_price_cents": unit_price,
            "line_total_cents": qty * unit_price,
        })
    if not cleaned:
        raise DomainError("El documento necesita al menos una linea.")
    return cleaned


def create_document(conn: sqlite3.Connection, *, kind: str, lines: list[dict[str, Any]],
                    party_name: str = "", party_tax_id: str = "", party_address: str = "",
                    notes: str = "", created_by: int | None = None,
                    origin_id: int | None = None) -> int:
    if kind not in KIND_PREFIX:
        raise DomainError(f"Tipo de documento invalido: {kind}")
    cleaned = _validate_lines(lines)

    total = Money(sum(line["line_total_cents"] for line in cleaned))
    subtotal, iva = split_iva(total)
    number = _next_number(conn, kind)

    cur = conn.execute(
        """INSERT INTO documents
               (kind, number, status, party_name, party_tax_id, party_address, notes,
                subtotal_cents, iva_cents, total_cents, origin_id, created_by)
           VALUES (?, ?, 'borrador', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (kind, number, party_name, party_tax_id, party_address, notes,
         subtotal.cents, iva.cents, total.cents, origin_id, created_by),
    )
    doc_id = int(cur.lastrowid)
    for line in cleaned:
        conn.execute(
            """INSERT INTO document_lines
                   (document_id, product_id, description, qty, unit_price_cents, line_total_cents)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (doc_id, line["product_id"], line["description"], line["qty"],
             line["unit_price_cents"], line["line_total_cents"]),
        )
    conn.commit()
    return doc_id


def issue_document(conn: sqlite3.Connection, document_id: int) -> None:
    """Mark a document as issued and apply its stock effect, exactly once."""
    doc = get_document(conn, document_id)
    if doc["status"] == "anulada":
        raise DomainError("No se puede emitir un documento anulado.")
    if doc["status"] == "emitida":
        raise DomainError("El documento ya fue emitido.")

    effect = ISSUE_EFFECT.get(doc["kind"])
    if effect:
        kind, sign = effect
        for line in doc["lines"]:
            if line["product_id"] is None:
                continue
            record_movement(conn, product_id=line["product_id"], qty=sign * line["qty"],
                            kind=kind, ref_type="document", ref_id=document_id,
                            note=f"{doc['number']}", commit=False)

    conn.execute(
        "UPDATE documents SET status = 'emitida', issued_at = datetime('now') WHERE id = ?",
        (document_id,),
    )
    conn.commit()


def receive_purchase_order(conn: sqlite3.Connection, document_id: int) -> None:
    """Receive an issued purchase order, adding its lines to stock."""
    doc = get_document(conn, document_id)
    if doc["kind"] != "orden_compra":
        raise DomainError("Solo las ordenes de compra se pueden recibir.")
    if doc["status"] != "emitida":
        raise DomainError("Emite la orden de compra antes de recibirla.")
    for line in doc["lines"]:
        if line["product_id"] is None:
            continue
        record_movement(conn, product_id=line["product_id"], qty=line["qty"],
                        kind="entrada", ref_type="document", ref_id=document_id,
                        note=f"Recepcion {doc['number']}", commit=False)
    conn.execute("UPDATE documents SET status = 'recibida' WHERE id = ?", (document_id,))
    conn.commit()


def convert_document(conn: sqlite3.Connection, document_id: int, target_kind: str,
                     created_by: int | None = None) -> int:
    """Create a new document of `target_kind` copying the lines of an existing one."""
    doc = get_document(conn, document_id)
    if target_kind not in KIND_PREFIX:
        raise DomainError(f"Tipo de documento invalido: {target_kind}")
    if doc["kind"] == "venta" and target_kind == "nota_credito":
        pass  # returns are the documented exception
    elif doc["kind"] not in {"cotizacion", "nota_venta"}:
        raise DomainError(f"No se puede convertir {doc['kind']} a {target_kind}.")
    lines = [{"product_id": l["product_id"], "description": l["description"],
              "qty": l["qty"], "unit_price_cents": l["unit_price_cents"]}
             for l in doc["lines"]]
    return create_document(conn, kind=target_kind, lines=lines, party_name=doc["party_name"],
                           party_tax_id=doc["party_tax_id"], party_address=doc["party_address"],
                           notes=doc["notes"], created_by=created_by, origin_id=document_id)


def get_document(conn: sqlite3.Connection, document_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        raise DomainError("El documento no existe.")
    doc = dict(row)
    lines = conn.execute(
        "SELECT * FROM document_lines WHERE document_id = ? ORDER BY id", (document_id,)
    ).fetchall()
    doc["lines"] = [dict(l) for l in lines]
    return doc


def list_documents(conn: sqlite3.Connection, *, kind: str | None = None) -> list[dict[str, Any]]:
    if kind:
        rows = conn.execute(
            "SELECT * FROM documents WHERE kind = ? ORDER BY id DESC", (kind,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM documents ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def dashboard(conn: sqlite3.Connection) -> dict[str, Any]:
    """Small set of numbers for the home view."""
    totals = conn.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN kind = 'venta' AND status IN ('emitida') THEN total_cents END), 0) AS vendido,
             COUNT(CASE WHEN kind = 'venta' AND status = 'emitida' THEN 1 END) AS n_ventas,
             COUNT(CASE WHEN status = 'borrador' THEN 1 END) AS borradores
           FROM documents"""
    ).fetchone()
    stock_value = conn.execute(
        """SELECT COALESCE(SUM(s.qty * p.cost_cents), 0) AS value
           FROM (SELECT product_id, SUM(qty) AS qty FROM stock_movements GROUP BY product_id) s
           JOIN products p ON p.id = s.product_id"""
    ).fetchone()
    return {
        "vendido_cents": int(totals["vendido"]),
        "n_ventas": int(totals["n_ventas"]),
        "borradores": int(totals["borradores"]),
        "stock_value_cents": int(stock_value["value"]),
        "productos": len(list_products(conn)),
        "bajo_stock": len(low_stock(conn)),
    }
