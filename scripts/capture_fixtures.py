"""Captura los datos del backend real para el demo estatico.

Requiere que la app este corriendo con datos sembrados, por ejemplo:

    python -m app.seed
    uvicorn app.api:app --port 8090
    BASE=http://127.0.0.1:8090 python scripts/capture_fixtures.py
"""
import json
import os
import pathlib
import urllib.request

BASE = os.environ.get("BASE", "http://127.0.0.1:8090")
DESTINO = pathlib.Path(__file__).resolve().parent.parent / "demo" / "data" / "fixtures.json"

_cookies: dict[str, str] = {}


def call(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if _cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in _cookies.items()))
    with urllib.request.urlopen(req) as res:
        for header in res.headers.get_all("Set-Cookie") or []:
            name, _, value = header.split(";")[0].partition("=")
            _cookies[name] = value
        raw = res.read()
        return json.loads(raw) if raw else None


def main() -> None:
    call("/api/auth/login", "POST", {"username": "admin", "password": "admin123"})

    fixtures = {
        "me": call("/api/auth/me"),
        "products": call("/api/products"),
        "movements": call("/api/movements"),
        "documents": call("/api/documents"),
        "dashboard": call("/api/dashboard"),
    }

    for kind in ["cotizacion", "nota_venta", "venta", "orden_compra", "nota_credito"]:
        fixtures[f"documents_{kind}"] = call(f"/api/documents?kind={kind}")

    fixtures["document_details"] = {
        str(doc["id"]): call(f"/api/documents/{doc['id']}")
        for doc in fixtures["documents"]
    }

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(fixtures, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"fixtures escritos en {DESTINO}")
    print(
        f"  productos={len(fixtures['products'])} "
        f"movimientos={len(fixtures['movements'])} "
        f"documentos={len(fixtures['documents'])}"
    )


if __name__ == "__main__":
    main()
