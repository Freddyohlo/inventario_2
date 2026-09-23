import pytest

from app import repo
from app.db import connect, init_db


@pytest.fixture()
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    init_db(connection)
    yield connection
    connection.close()


@pytest.fixture()
def product(conn):
    return repo.create_product(conn, sku="P-1", name="Cemento", cost_cents=300000,
                              price_cents=450000, min_stock=5)


def test_stock_starts_at_zero(conn, product):
    assert repo.stock_level(conn, product) == 0


def test_sale_decreases_stock(conn, product):
    doc = repo.create_document(conn, kind="venta", lines=[
        {"product_id": product, "qty": 3, "unit_price_cents": 450000},
    ])
    repo.issue_document(conn, doc)
    assert repo.stock_level(conn, product) == -3


def test_purchase_order_only_adds_stock_when_received(conn, product):
    doc = repo.create_document(conn, kind="orden_compra", lines=[
        {"product_id": product, "qty": 20, "unit_price_cents": 300000},
    ])
    repo.issue_document(conn, doc)
    assert repo.stock_level(conn, product) == 0, "emitir no debe sumar stock"

    repo.receive_purchase_order(conn, doc)
    assert repo.stock_level(conn, product) == 20


def test_receiving_twice_is_rejected(conn, product):
    doc = repo.create_document(conn, kind="orden_compra", lines=[
        {"product_id": product, "qty": 5, "unit_price_cents": 100},
    ])
    repo.issue_document(conn, doc)
    repo.receive_purchase_order(conn, doc)
    with pytest.raises(repo.DomainError):
        repo.receive_purchase_order(conn, doc)
    assert repo.stock_level(conn, product) == 5


def test_issuing_twice_writes_stock_once(conn, product):
    doc = repo.create_document(conn, kind="venta", lines=[
        {"product_id": product, "qty": 2, "unit_price_cents": 100},
    ])
    repo.issue_document(conn, doc)
    with pytest.raises(repo.DomainError):
        repo.issue_document(conn, doc)
    assert repo.stock_level(conn, product) == -2


def test_credit_note_returns_stock(conn, product):
    sale = repo.create_document(conn, kind="venta", lines=[
        {"product_id": product, "qty": 4, "unit_price_cents": 100},
    ])
    repo.issue_document(conn, sale)
    credit = repo.convert_document(conn, sale, "nota_credito")
    repo.issue_document(conn, credit)
    assert repo.stock_level(conn, product) == 0


def test_quote_to_sale_keeps_lines_and_links_origin(conn, product):
    quote = repo.create_document(conn, kind="cotizacion", lines=[
        {"product_id": product, "qty": 2, "unit_price_cents": 450000},
        {"product_id": product, "qty": 1, "unit_price_cents": 450000},
    ], party_name="Cliente X")
    sale = repo.convert_document(conn, quote, "venta")

    quote_doc = repo.get_document(conn, quote)
    sale_doc = repo.get_document(conn, sale)
    assert sale_doc["origin_id"] == quote
    assert sale_doc["party_name"] == "Cliente X"
    assert [l["qty"] for l in sale_doc["lines"]] == [2, 1]
    assert sale_doc["kind"] == "venta"
    # the quote itself does not touch stock
    assert repo.stock_level(conn, product) == 0
    repo.issue_document(conn, sale)
    assert repo.stock_level(conn, product) == -3
    assert quote_doc["status"] == "borrador"


def test_document_numbers_are_sequential_and_prefixed(conn):
    a = repo.create_document(conn, kind="venta", lines=[{"qty": 1, "unit_price_cents": 100}])
    b = repo.create_document(conn, kind="venta", lines=[{"qty": 1, "unit_price_cents": 100}])
    c = repo.create_document(conn, kind="cotizacion", lines=[{"qty": 1, "unit_price_cents": 100}])
    assert repo.get_document(conn, a)["number"] == "VTA-00001"
    assert repo.get_document(conn, b)["number"] == "VTA-00002"
    assert repo.get_document(conn, c)["number"] == "COT-00001"


def test_iva_is_split_on_the_document(conn):
    doc = repo.create_document(conn, kind="venta", lines=[{"qty": 1, "unit_price_cents": 11900}])
    data = repo.get_document(conn, doc)
    assert data["total_cents"] == 11900
    assert data["subtotal_cents"] == 10000
    assert data["iva_cents"] == 1900


def test_empty_document_is_rejected(conn):
    with pytest.raises(repo.DomainError):
        repo.create_document(conn, kind="venta", lines=[])


def test_zero_or_negative_quantity_is_rejected(conn):
    with pytest.raises(repo.DomainError):
        repo.create_document(conn, kind="venta", lines=[{"qty": 0, "unit_price_cents": 100}])


def test_duplicate_sku_is_rejected(conn, product):
    with pytest.raises(repo.DomainError):
        repo.create_product(conn, sku="P-1", name="Otro")


def test_free_text_line_without_product(conn):
    doc = repo.create_document(conn, kind="venta", lines=[
        {"product_id": None, "description": "Servicio de instalación", "qty": 1, "unit_price_cents": 50000},
    ])
    repo.issue_document(conn, doc)
    assert repo.stock_level(conn, 1) == 0


def test_low_stock_uses_ledger_sum(conn, product):
    assert [p["id"] for p in repo.low_stock(conn)] == [product]
    repo.record_movement(conn, product_id=product, qty=10, kind="entrada")
    assert repo.low_stock(conn) == []


def test_dashboard_totals(conn, product):
    sale = repo.create_document(conn, kind="venta", lines=[
        {"product_id": product, "qty": 2, "unit_price_cents": 450000},
    ])
    repo.issue_document(conn, sale)
    repo.record_movement(conn, product_id=product, qty=10, kind="entrada")

    dash = repo.dashboard(conn)
    assert dash["vendido_cents"] == 900000
    assert dash["n_ventas"] == 1
    assert dash["productos"] == 1
    # 10 in, 2 sold out => 8 units left, valued at cost
    assert repo.stock_level(conn, product) == 8
    assert dash["stock_value_cents"] == 8 * 300000
