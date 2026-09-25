"""Genera demo/app.js a partir del frontend real.

Toma static/js/app.js y reemplaza solo la capa de red: en vez de llamar a la API
lee demo/data/fixtures.json, y bloquea cualquier escritura. El resto del
frontend (render, estilos, eventos) queda intacto, para que la demo muestre la
interfaz real.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ORIGEN = ROOT / "static" / "js" / "app.js"
DESTINO = ROOT / "demo" / "app.js"

INICIO_API = "/* ── API ─"
FIN_API = "/* ── Estado ─"

NUEVA_API = '''/* ── Datos locales (demo estática) ─────────────────────────────────────── */
async function cargarDatos() {
  const res = await fetch('data/fixtures.json');
  return res.json();
}

let DATOS = null;
const esperarDatos = cargarDatos().then((d) => { DATOS = d; return d; });

const SIN_FUNCIONALIDAD =
  'Esta es una demo visual: la interfaz es real, pero no crea ni modifica datos.';

async function api(path, { method = 'GET', body } = {}) {
  const d = DATOS || (await esperarDatos);
  const [ruta, query] = path.split('?');
  const params = new URLSearchParams(query || '');

  // Cualquier escritura se bloquea con un aviso.
  if (method !== 'GET') {
    if (ruta === '/api/auth/login') return d.me;   // el login solo muestra el panel
    if (ruta === '/api/auth/logout') return null;
    toast(SIN_FUNCIONALIDAD, 'bad');
    throw new Error(SIN_FUNCIONALIDAD);
  }

  if (ruta === '/api/auth/me') return d.me;
  if (ruta === '/api/dashboard') return d.dashboard;
  if (ruta === '/api/products') return d.products;
  if (ruta === '/api/movements') return d.movements;
  if (ruta === '/api/documents') {
    const kind = params.get('kind');
    return kind ? (d['documents_' + kind] || []) : d.documents;
  }
  const detalle = ruta.match(/^\\/api\\/documents\\/(\\d+)$/);
  if (detalle) return d.document_details[detalle[1]] || null;

  throw new Error('Ruta no disponible en la demo: ' + path);
}

/* Aviso permanente de que es una demo. */
function montarAvisoDemo() {
  const barra = document.createElement('div');
  barra.className = 'demo-aviso';
  barra.setAttribute('role', 'status');
  barra.innerHTML =
    '<b>Demo</b> · Solo para mostrar la interfaz. No crea ni modifica datos.';
  const main = document.querySelector('.main');
  if (main) main.prepend(barra);
}

'''

BOOT_VIEJO = (
    "async function boot() {\n"
    "  try {\n"
    "    showApp(await api('/api/auth/me'));\n"
    "  } catch {\n"
    "    showLogin();\n"
    "  }\n"
    "}"
)
BOOT_NUEVO = (
    "async function boot() {\n"
    "  await esperarDatos;\n"
    "  showApp(DATOS.me);\n"
    "  montarAvisoDemo();\n"
    "}"
)


def main() -> None:
    src = ORIGEN.read_text(encoding="utf-8")

    inicio = src.index(INICIO_API)
    fin = src.index(FIN_API)
    out = src[:inicio] + NUEVA_API + src[fin:]

    if BOOT_VIEJO not in out:
        raise SystemExit("No se encontró la función boot() esperada en static/js/app.js")
    out = out.replace(BOOT_VIEJO, BOOT_NUEVO)

    DESTINO.write_text(out, encoding="utf-8")
    print(f"demo generado en {DESTINO}")


if __name__ == "__main__":
    main()
