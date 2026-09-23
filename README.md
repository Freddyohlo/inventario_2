# Bodega — demo de inventario para PYME

Demo funcional de un sistema de inventario y documentos para una pyme: ventas
que descuentan stock, órdenes de compra que lo reponen, cotizaciones que se
convierten en nota de venta, y notas de crédito para devoluciones. Todo con
historial auditable.

> Este repositorio es un **demo**. Ver "Alcance y límites" antes de usarlo con
> datos reales de un negocio.

## Qué incluye

| Módulo | Comportamiento |
| --- | --- |
| **Inventario** | Catálogo con SKU, costo, precio, margen calculado, stock y mínimo. Alerta de reposición. |
| **Movimientos** | Libro de stock append-only: cada entrada, salida y ajuste queda registrado con su referencia. |
| **Cotización** | Documento numerado. No toca stock. Se convierte en nota de venta o venta con un clic. |
| **Nota de venta** | Documento interno de respaldo. No toca stock. Convertible a venta. |
| **Venta** | Al emitirse **descuenta stock** generando un movimiento. |
| **Orden de compra** | Al emitirse no toca stock; al **recibirse** suma stock. No se puede recibir dos veces. |
| **Nota de crédito** | Devuelve stock al emitirse. Se genera desde una venta. |

## Cómo funciona el stock

El stock no es una columna que se sobrescribe. Es la **suma de un libro de
movimientos**. Una venta escribe un movimiento negativo; una recepción de compra
escribe uno positivo. Eso hace que:

- el historial sea auditable (quién movió qué y por qué),
- emitir dos veces un documento sea imposible (el segundo intento se rechaza),
- y el stock sea siempre reconstruible desde cero.

El dinero se maneja en **enteros de centavos**, nunca en `float`, para que el IVA
y los totales no arrastren errores de redondeo. Al partir un monto bruto, el neto
absorbe el resto, así que `neto + IVA == bruto` exactamente.

## Requisitos

- Python 3.10 o superior

## Puesta en marcha

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Datos de ejemplo (productos, una compra recibida, ventas, una cotización
# convertida, una nota de venta y una nota de crédito)
python -m app.seed

uvicorn app.api:app --reload
```

Abre <http://127.0.0.1:8000> e ingresa con:

| Usuario | Clave | Rol |
| --- | --- | --- |
| `admin` | `admin123` | Administrador |
| `vendedor` | `vende123` | Vendedor |

Los usuarios se crean solos la primera vez que arranca la app (o al correr el
seed). Se pueden cambiar con `ADMIN_USER` y `ADMIN_PASSWORD`.

### Variables de entorno

| Variable | Por defecto | Para qué |
| --- | --- | --- |
| `DB_PATH` | `data/inventario.db` | Ruta del archivo SQLite |
| `SECRET_KEY` | `dev-insecure-key` | Firma de la cookie de sesión. **Cámbiala** |
| `ADMIN_USER` / `ADMIN_PASSWORD` | `admin` / `admin123` | Administrador inicial |

## Roles

| Acción | Administrador | Vendedor |
| --- | :---: | :---: |
| Ver catálogo, panel y documentos | sí | sí |
| Crear y emitir ventas, notas de venta, cotizaciones | sí | sí |
| Crear y recibir órdenes de compra | sí | no |
| Crear y editar productos, registrar movimientos | sí | no |

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest -q          # 46 pruebas: dinero, dominio, auth y API
```

Con el servidor corriendo, un recorrido funcional contra la API real:

```bash
python scripts/smoke.py http://127.0.0.1:8000
```

## Estructura

```
app/
  money.py    Dinero en enteros y reparto de IVA exacto
  db.py       Esquema SQLite y conexión
  repo.py     Dominio: productos, libro de stock, documentos
  auth.py     Hash PBKDF2 y sesiones firmadas
  api.py      Endpoints FastAPI y montaje del frontend
  seed.py     Datos de ejemplo
static/       Frontend (HTML, CSS y JS, sin build step)
tests/        Pruebas de dinero, dominio, auth y API
scripts/      smoke.py
```

## Estructura de la interfaz

El frontend es **HTML, CSS y JavaScript sin framework ni build step**. Habla
únicamente con la API, que es la única fuente de verdad de montos y stock; el
navegador no calcula totales definitivos, solo los previsualiza.

La dirección visual es de **libro mayor editorial**: papel crema, tinta verde
profunda, acento terracota, serif Fraunces para títulos, Archivo para texto y
cifras tabulares alineadas a la derecha en las columnas numéricas.

## Alcance y límites

Pensado para un demo. Antes de usarlo con datos reales de un negocio:

- **Los documentos no son tributarios.** No hay folios del SII, ni timbraje, ni
  certificación, ni DTE. La numeración es interna y correlativa por tipo. Emitir
  documentos con validez tributaria es un proyecto aparte (idealmente integrado
  con un proveedor de facturación electrónica).
- **La autenticación es básica.** PBKDF2 con sal para las claves y cookie
  firmada, pero **no hay HTTPS, ni expiración por inactividad, ni bloqueo por
  intentos, ni recuperación de clave**. No la expongas a internet tal como está.
- **SQLite y un solo proceso.** Suficiente para un local; para varios usuarios
  simultáneos de verdad, migra a PostgreSQL.
- **El stock permite negativos.** No se bloquea vender sin stock, para no frenar
  una venta de mostrador. Si lo prefieres, se puede convertir en un error.
- **Sin impresión en PDF todavía.** Los documentos se ven en pantalla. La salida
  a PDF es el siguiente paso natural.
- **Sin auditoría de usuarios por documento** más allá del `created_by`.

## Próximos pasos sugeridos

1. Salida de documentos a PDF e impresión.
2. Migrar a PostgreSQL si hay concurrencia real.
3. Cierre de caja diario y reportes por período.
4. Búsqueda y filtros en el catálogo y en los listados.
5. Integración con facturación electrónica si se necesitan documentos tributarios.

