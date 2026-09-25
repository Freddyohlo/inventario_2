"""Live smoke test against a running server.

Usage: python scripts/smoke.py [base_url]
Default base URL comes from SMOKE_BASE or http://127.0.0.1:8000
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("SMOKE_BASE", "http://127.0.0.1:8000")
if len(sys.argv) > 1:
    BASE = sys.argv[1]
_cookies = {}


def call(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if _cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in _cookies.items()))
    try:
        with urllib.request.urlopen(req) as res:
            for header in res.headers.get_all("Set-Cookie") or []:
                name, _, value = header.split(";")[0].partition("=")
                _cookies[name] = value
            return res.status, json.loads(res.read() or "null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or "null")


def check(label, condition, detail=""):
    mark = "ok  " if condition else "FAIL"
    print(f"  [{mark}] {label}{(' — ' + detail) if detail else ''}")
    return condition


def main():
    failures = 0
    print("Recorrido en vivo")

    status, _ = call("/api/products")
    failures += not check("sin sesión responde 401", status == 401, f"status={status}")

    status, user = call("/api/auth/login", "POST", {"username": "admin", "password": "admin123"})
    failures += not check("login admin", status == 200 and user["role"] == "admin")

    status, products = call("/api/products")
    failures += not check("catálogo sembrado", status == 200 and len(products) >= 6,
                          f"{len(products) if isinstance(products, list) else '?'} productos")

    status, dash = call("/api/dashboard")
    failures += not check("panel con ventas", dash["n_ventas"] >= 2, f"vendido={dash['vendido']}")
    failures += not check("reposición con contenido", dash["bajo_stock"] == 1,
                          f"{dash['bajo_stock']} por reponer")

    status, newp = call("/api/products", "POST", {
        "sku": "SMK-001", "name": "Producto smoke", "cost_cents": 100000, "price_cents": 200000,
    })
    failures += not check("crear producto", status == 201, f"status={status}")
    pid = newp.get("id")

    status, doc = call("/api/documents", "POST", {
        "kind": "venta", "party_name": "Smoke Test",
        "lines": [{"product_id": pid, "description": "Producto smoke", "qty": 4, "unit_price_cents": 238000}],
    })
    failures += not check("crear venta", status == 201, doc.get("number", str(doc)))
    failures += not check("IVA calculado", doc.get("subtotal") == "8000.00" and doc.get("iva") == "1520.00",
                          f"neto={doc.get('subtotal')} iva={doc.get('iva')} total={doc.get('total')}")

    status, _ = call(f"/api/documents/{doc['id']}/issue", "POST")
    failures += not check("emitir venta", status == 200)

    status, products = call("/api/products")
    stock = next((p["stock"] for p in products if p["sku"] == "SMK-001"), None)
    failures += not check("la venta descontó stock", stock == -4, f"stock={stock}")

    status, again = call(f"/api/documents/{doc['id']}/issue", "POST")
    failures += not check("no se puede emitir dos veces", status == 400, again.get("detail", ""))

    status, movements = call("/api/movements")
    ref = next((m for m in movements if m["note"] == doc["number"]), None)
    failures += not check("el libro registró el movimiento", ref is not None and ref["qty"] == -4)

    status, quote = call("/api/documents", "POST", {
        "kind": "cotizacion", "party_name": "Smoke",
        "lines": [{"product_id": pid, "qty": 2, "unit_price_cents": 238000}],
    })
    status, sale = call(f"/api/documents/{quote['id']}/convert", "POST", {"target_kind": "venta"})
    failures += not check("cotización se convierte en venta",
                          status == 201 and sale.get("origin_id") == quote["id"])

    status, _ = call("/api/auth/logout", "POST")
    status, _ = call("/api/auth/login", "POST", {"username": "vendedor", "password": "vende123"})
    status, res = call("/api/products", "POST", {"sku": "SMK-002", "name": "Nope"})
    failures += not check("vendedor no crea productos", status == 403)

    status, res = call("/api/documents", "POST", {
        "kind": "orden_compra", "lines": [{"qty": 1, "unit_price_cents": 100}],
    })
    failures += not check("vendedor no crea orden de compra", status == 403)

    print()
    if failures:
        print(f"{failures} comprobación(es) fallaron")
        return 1
    print("Todo el recorrido pasó")
    return 0


if __name__ == "__main__":
    sys.exit(main())
