"""API-level tests: authentication, role gates and the stock effect of issuing."""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    from app import api as api_module
    importlib.reload(api_module)
    api_module.bootstrap()

    with TestClient(api_module.app) as c:
        # a seller account alongside the bootstrapped admin
        conn = api_module.connect(api_module.DB_PATH)
        from app import auth
        auth.create_user(conn, username="vendedor", password="vende123", role=auth.ROLE_SELLER)
        conn.close()
        yield c


def login(client, username="admin", password="admin123"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res


def test_requires_authentication(client):
    assert client.get("/api/products").status_code == 401
    assert client.get("/api/dashboard").status_code == 401


def test_login_and_me(client):
    login(client)
    assert client.get("/api/auth/me").json()["role"] == "admin"


def test_bad_credentials_rejected(client):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401


def test_product_creation_is_admin_only(client):
    login(client, "vendedor", "vende123")
    res = client.post("/api/products", json={"sku": "S-1", "name": "X", "price_cents": 100})
    assert res.status_code == 403


def test_creating_a_product_and_listing_it(client):
    login(client)
    assert client.post("/api/products", json={
        "sku": "P-1", "name": "Cemento", "cost_cents": 300000, "price_cents": 450000, "min_stock": 2,
    }).status_code == 201
    products = client.get("/api/products").json()
    assert products[0]["sku"] == "P-1"
    assert products[0]["price"] == "4500.00"
    assert products[0]["low"] is True


def test_duplicate_sku_returns_400(client):
    login(client)
    body = {"sku": "P-1", "name": "Cemento"}
    client.post("/api/products", json=body)
    res = client.post("/api/products", json=body)
    assert res.status_code == 400
    assert "ya existe" in res.json()["detail"]


def test_sale_flow_through_the_api(client):
    login(client)
    pid = client.post("/api/products", json={
        "sku": "P-1", "name": "Cemento", "cost_cents": 300000, "price_cents": 119000,
    }).json()["id"]

    doc = client.post("/api/documents", json={
        "kind": "venta",
        "lines": [{"product_id": pid, "description": "Cemento", "qty": 3, "unit_price_cents": 119000}],
        "party_name": "Constructora Ltda",
    }).json()
    assert doc["number"] == "VTA-00001"
    assert doc["total"] == "3570.00"

    issued = client.post(f"/api/documents/{doc['id']}/issue").json()
    assert issued["status"] == "emitida"

    product = client.get("/api/products").json()[0]
    assert product["stock"] == -3

    movements = client.get("/api/movements").json()
    assert movements[0]["qty"] == -3
    assert movements[0]["note"] == "VTA-00001"


def test_purchase_order_role_gate_and_receipt(client):
    login(client)
    pid = client.post("/api/products", json={"sku": "P-1", "name": "Cemento", "cost_cents": 300000}).json()["id"]
    doc = client.post("/api/documents", json={
        "kind": "orden_compra",
        "lines": [{"product_id": pid, "qty": 10, "unit_price_cents": 300000}],
    }).json()
    client.post(f"/api/documents/{doc['id']}/issue")

    # a seller may not receive stock
    client.post("/api/auth/logout")
    login(client, "vendedor", "vende123")
    assert client.post(f"/api/documents/{doc['id']}/receive").status_code == 403

    client.post("/api/auth/logout")
    login(client)
    assert client.post(f"/api/documents/{doc['id']}/receive").status_code == 200
    assert client.get("/api/products").json()[0]["stock"] == 10


def test_seller_cannot_create_purchase_order(client):
    client.post("/api/auth/login", json={"username": "vendedor", "password": "vende123"})
    res = client.post("/api/documents", json={
        "kind": "orden_compra", "lines": [{"qty": 1, "unit_price_cents": 100}],
    })
    assert res.status_code == 403


def test_seller_can_create_a_sale(client):
    login(client, "vendedor", "vende123")
    res = client.post("/api/documents", json={
        "kind": "venta", "lines": [{"qty": 1, "unit_price_cents": 100}],
    })
    assert res.status_code == 201


def test_quote_converts_to_sale_and_then_moves_stock(client):
    login(client)
    pid = client.post("/api/products", json={"sku": "P-1", "name": "Cemento"}).json()["id"]
    quote = client.post("/api/documents", json={
        "kind": "cotizacion", "party_name": "Cliente",
        "lines": [{"product_id": pid, "qty": 5, "unit_price_cents": 1000}],
    }).json()
    assert client.get("/api/products").json()[0]["stock"] == 0

    sale = client.post(f"/api/documents/{quote['id']}/convert", json={"target_kind": "venta"}).json()
    assert sale["origin_id"] == quote["id"]
    client.post(f"/api/documents/{sale['id']}/issue")
    assert client.get("/api/products").json()[0]["stock"] == -5


def test_document_not_found_returns_404(client):
    login(client)
    assert client.get("/api/documents/999").status_code == 404


def test_invalid_document_kind_returns_400(client):
    login(client)
    res = client.post("/api/documents", json={"kind": "factura", "lines": [{"qty": 1, "unit_price_cents": 1}]})
    assert res.status_code == 400


def test_dashboard_shape(client):
    login(client)
    data = client.get("/api/dashboard").json()
    assert set(data) >= {"vendido", "n_ventas", "productos", "bajo_stock", "stock_value", "low_stock"}
    assert data["vendido"] == "0.00"
