"""SQLite schema and connection handling.

The design keeps stock as an append-only ledger rather than a mutable column:
every purchase receipt and sale writes a movement row, and the product's stock is
the sum of its movements. That makes history auditable and avoids silently
overwriting quantities.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'vendedor')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sku           TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    unit          TEXT NOT NULL DEFAULT 'un',
    cost_cents    INTEGER NOT NULL DEFAULT 0,
    price_cents   INTEGER NOT NULL DEFAULT 0,
    min_stock     INTEGER NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    qty         INTEGER NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('entrada', 'salida', 'ajuste')),
    ref_type    TEXT,
    ref_id      INTEGER,
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mov_product ON stock_movements(product_id);

CREATE TABLE IF NOT EXISTS documents (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT NOT NULL CHECK (kind IN ('cotizacion', 'nota_venta', 'venta', 'orden_compra', 'nota_credito')),
    number         TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'borrador',
    party_name     TEXT NOT NULL DEFAULT '',
    party_tax_id   TEXT NOT NULL DEFAULT '',
    party_address  TEXT NOT NULL DEFAULT '',
    notes          TEXT NOT NULL DEFAULT '',
    subtotal_cents INTEGER NOT NULL DEFAULT 0,
    iva_cents      INTEGER NOT NULL DEFAULT 0,
    total_cents    INTEGER NOT NULL DEFAULT 0,
    origin_id      INTEGER REFERENCES documents(id),
    created_by     INTEGER REFERENCES users(id),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    issued_at      TEXT,
    UNIQUE (kind, number)
);

CREATE TABLE IF NOT EXISTS document_lines (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    product_id    INTEGER REFERENCES products(id),
    description   TEXT NOT NULL DEFAULT '',
    qty           INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    line_total_cents INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lines_doc ON document_lines(document_id);

CREATE TABLE IF NOT EXISTS counters (
    kind  TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with row access by name and foreign keys enforced.

    ``check_same_thread=False`` is required because FastAPI runs sync
    dependencies and endpoints on a threadpool, so a request's connection can be
    created on one worker thread and used on another. One connection is opened
    per request and never shared across requests.
    """
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
