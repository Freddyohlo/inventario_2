"""HTTP API and static frontend for the inventory demo."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, repo
from .db import connect, init_db
from .money import Money

DB_PATH = os.environ.get("DB_PATH", "data/inventario.db")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Inventario PYME", docs_url="/api/docs", openapi_url="/api/openapi.json")
sessions = auth.SessionManager()


def get_db() -> Iterator[Any]:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def current_user(
    conn: Any = Depends(get_db),
    inventario_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    if not inventario_session:
        raise HTTPException(status_code=401, detail="No autenticado")
    payload = sessions.read(inventario_session)
    if not payload:
        raise HTTPException(status_code=401, detail="Sesion expirada")
    row = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (payload["uid"],)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Usuario inexistente")
    return dict(row)


def require_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user["role"] != auth.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Requiere rol administrador")
    return user


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

class LoginIn(BaseModel):
    username: str
    password: str


class ProductIn(BaseModel):
    sku: str
    name: str
    unit: str = "un"
    cost_cents: int = 0
    price_cents: int = 0
    min_stock: int = 0


class LineIn(BaseModel):
    product_id: int | None = None
    description: str = ""
    qty: int = Field(gt=0)
    unit_price_cents: int = Field(ge=0)


class DocumentIn(BaseModel):
    kind: str
    lines: list[LineIn]
    party_name: str = ""
    party_tax_id: str = ""
    party_address: str = ""
    notes: str = ""


class ConvertIn(BaseModel):
    target_kind: str


class MovementIn(BaseModel):
    product_id: int
    qty: int
    kind: str = "ajuste"
    note: str = ""


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #

@app.post("/api/auth/login")
def login(data: LoginIn, response: Response, conn: Any = Depends(get_db)) -> dict[str, Any]:
    user = auth.authenticate(conn, data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario o clave incorrectos")
    response.set_cookie(
        sessions.COOKIE, sessions.sign(user),
        httponly=True, samesite="lax", max_age=auth.SESSION_MAX_AGE,
    )
    return user


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(sessions.COOKIE)
    return {"status": "ok"}


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return user


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #

def _product_out(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "cost": str(Money(row["cost_cents"])),
        "price": str(Money(row["price_cents"])),
        "low": row["stock"] <= row["min_stock"],
    }


@app.get("/api/products")
def products(conn: Any = Depends(get_db), _: dict = Depends(current_user)) -> list[dict[str, Any]]:
    return [_product_out(p) for p in repo.list_products(conn)]


@app.post("/api/products", status_code=201)
def add_product(data: ProductIn, conn: Any = Depends(get_db),
                _: dict = Depends(require_admin)) -> dict[str, Any]:
    try:
        pid = repo.create_product(conn, **data.model_dump())
    except repo.DomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": pid}


@app.post("/api/movements", status_code=201)
def add_movement(data: MovementIn, conn: Any = Depends(get_db),
                 _: dict = Depends(require_admin)) -> dict[str, str]:
    try:
        repo.record_movement(conn, **data.model_dump())
    except repo.DomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@app.get("/api/movements")
def movements(conn: Any = Depends(get_db), _: dict = Depends(current_user)) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT m.*, p.sku, p.name AS product_name
           FROM stock_movements m JOIN products p ON p.id = m.product_id
           ORDER BY m.id DESC LIMIT 200"""
    ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #

def _document_out(conn: Any, doc: dict[str, Any]) -> dict[str, Any]:
    return {
        **doc,
        "subtotal": str(Money(doc["subtotal_cents"])),
        "iva": str(Money(doc["iva_cents"])),
        "total": str(Money(doc["total_cents"])),
        "lines": [
            {**l, "unit_price": str(Money(l["unit_price_cents"])),
             "line_total": str(Money(l["line_total_cents"]))}
            for l in doc["lines"]
        ],
    }


@app.get("/api/documents")
def documents(kind: str | None = Query(default=None), conn: Any = Depends(get_db),
              _: dict = Depends(current_user)) -> list[dict[str, Any]]:
    return [
        {**d, "total": str(Money(d["total_cents"]))}
        for d in repo.list_documents(conn, kind=kind)
    ]


@app.get("/api/documents/{document_id}")
def document(document_id: int, conn: Any = Depends(get_db),
             _: dict = Depends(current_user)) -> dict[str, Any]:
    try:
        return _document_out(conn, repo.get_document(conn, document_id))
    except repo.DomainError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/documents", status_code=201)
def new_document(data: DocumentIn, conn: Any = Depends(get_db),
                 user: dict = Depends(current_user)) -> dict[str, Any]:
    if data.kind == "orden_compra" and user["role"] != auth.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Solo un administrador emite ordenes de compra")
    try:
        doc_id = repo.create_document(conn, created_by=user["id"], **data.model_dump())
    except repo.DomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _document_out(conn, repo.get_document(conn, doc_id))


@app.post("/api/documents/{document_id}/issue")
def issue(document_id: int, conn: Any = Depends(get_db),
          _: dict = Depends(current_user)) -> dict[str, Any]:
    try:
        repo.issue_document(conn, document_id)
    except repo.DomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _document_out(conn, repo.get_document(conn, document_id))


@app.post("/api/documents/{document_id}/receive")
def receive(document_id: int, conn: Any = Depends(get_db),
            _: dict = Depends(require_admin)) -> dict[str, Any]:
    try:
        repo.receive_purchase_order(conn, document_id)
    except repo.DomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _document_out(conn, repo.get_document(conn, document_id))


@app.post("/api/documents/{document_id}/convert", status_code=201)
def convert(document_id: int, data: ConvertIn, conn: Any = Depends(get_db),
            user: dict = Depends(current_user)) -> dict[str, Any]:
    try:
        new_id = repo.convert_document(conn, document_id, data.target_kind, created_by=user["id"])
    except repo.DomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _document_out(conn, repo.get_document(conn, new_id))


# --------------------------------------------------------------------------- #
# Dashboard and frontend
# --------------------------------------------------------------------------- #

@app.get("/api/dashboard")
def dashboard(conn: Any = Depends(get_db), _: dict = Depends(current_user)) -> dict[str, Any]:
    data = repo.dashboard(conn)
    return {
        **data,
        "vendido": str(Money(data["vendido_cents"])),
        "stock_value": str(Money(data["stock_value_cents"])),
        "low_stock": [_product_out(p) for p in repo.low_stock(conn)],
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def bootstrap() -> None:
    """Create the schema and a default admin on first run."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(DB_PATH)
    init_db(conn)
    if conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0:
        auth.create_user(conn, username=os.environ.get("ADMIN_USER", "admin"),
                         password=os.environ.get("ADMIN_PASSWORD", "admin123"),
                         role=auth.ROLE_ADMIN)
    conn.close()


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
