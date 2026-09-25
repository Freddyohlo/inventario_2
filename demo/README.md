# Bodega (demo visual)

Demo **estática** de la interfaz de Bodega, pensada para mostrar cómo se ve la
aplicación sin necesidad de backend ni base de datos.

> **Solo para mostrar la interfaz.** No crea, modifica ni guarda datos.
> Los formularios están deshabilitados a propósito.

## Qué incluye

Toda la interfaz real: panel con indicadores, catálogo de inventario con margen
calculado, libro de movimientos, y los cinco tipos de documento (cotización,
nota de venta, venta, orden de compra y nota de crédito) con su detalle.

Los datos son un **fixture capturado del backend real** (`data/fixtures.json`),
generado por `app/seed.py`. No son inventados.

## Cómo funciona

Es el mismo frontend de la app (`static/`), con una sola diferencia: la capa de
red (`demo/app.js`) lee los datos de un JSON local en vez de llamar a la API.
Cualquier intento de escritura se bloquea en el navegador con un aviso.

No hay build step, ni framework, ni dependencias. Es HTML, CSS y JS.

## Desplegar en Vercel

Este directorio es estático, así que Vercel lo sirve tal cual:

1. **New Project** en Vercel → elegir el repo `inventario_2`.
2. En **Root Directory**, seleccionar **`demo`**.
3. Framework Preset: **Other**. Build Command: vacío. Output Directory: vacío.
4. Deploy.

El resultado carga al instante: no hay contenedor que despierte ni cold start.

## Regenerar el fixture

Si cambian los datos de ejemplo, se vuelve a capturar del backend real:

```bash
python -m app.seed
uvicorn app.api:app --port 8090
python scripts/capture_fixtures.py
python scripts/build_demo.py
```

## Estructura

```
index.html          Interfaz (mismo HTML de la app)
app.js              Frontend con la capa de datos local
style.css           Sistema de diseño de Bodega
data/fixtures.json  Datos de ejemplo capturados del backend
vercel.json         Configuración de despliegue estático
```
