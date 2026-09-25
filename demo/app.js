/* ==========================================================================
   Bodega — frontend
   Vanilla JS a propósito: sin build step, sin framework. El backend es la
   única fuente de verdad de los montos y del stock.
   ========================================================================== */

'use strict';

/* ── Iconos ────────────────────────────────────────────────────────────── */
const ICONS = {
  gauge:  '<path d="M4 13a8 8 0 1 1 16 0"/><path d="M12 13l3.5-3.5"/><circle cx="12" cy="13" r="1.4"/>',
  box:    '<path d="M3.5 8.2 12 3.5l8.5 4.7v7.6L12 20.5 3.5 15.8z"/><path d="M3.5 8.2 12 13l8.5-4.8M12 13v7.5"/>',
  arrows: '<path d="M7 4v16M7 20l-3-3M7 20l3-3"/><path d="M17 20V4M17 4l-3 3M17 4l3 3"/>',
  quote:  '<path d="M6 3.5h9l4 4V20.5H6z"/><path d="M15 3.5v4h4"/><path d="M9 12h6M9 15.5h4"/>',
  note:   '<path d="M5 3.5h14v17l-3-2-2 2-2-2-2 2-2-2-3 2z"/><path d="M9 9h6M9 13h6"/>',
  sale:   '<path d="M4 7h16l-1.4 11.5H5.4z"/><path d="M8.5 7V5.5a3.5 3.5 0 0 1 7 0V7"/>',
  cart:   '<circle cx="9.5" cy="19" r="1.3"/><circle cx="17.5" cy="19" r="1.3"/><path d="M3 4h2.2l2.4 11.2h11L21 7.5H6"/>',
  undo:   '<path d="M4 12a8 8 0 1 0 2.6-5.9"/><path d="M4 4v5h5"/>',
  plus:   '<path d="M12 5v14M5 12h14"/>',
  trash:  '<path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13"/>',
};

const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ''}</svg>`;

/* ── Formato ───────────────────────────────────────────────────────────── */
const moneyFmt = new Intl.NumberFormat('es-CL', {
  minimumFractionDigits: 0, maximumFractionDigits: 2,
});
const numberFmt = new Intl.NumberFormat('es-CL');

/** Recibe montos como string ("12.00") o número y devuelve "$12" o "$25,50". */
function money(value) {
  const n = typeof value === 'string' ? parseFloat(value) : Number(value || 0);
  return '$' + moneyFmt.format(isFinite(n) ? n : 0);
}
const qty = (n) => numberFmt.format(Number(n || 0));

const DOC_LABELS = {
  cotizacion:  { singular: 'Cotización',   plural: 'Cotizaciones',    icon: 'quote', effect: null },
  nota_venta:  { singular: 'Nota de venta', plural: 'Notas de venta',  icon: 'note',  effect: null },
  venta:       { singular: 'Venta',        plural: 'Ventas',           icon: 'sale',  effect: 'Descuenta stock' },
  orden_compra:{ singular: 'Orden de compra', plural: 'Órdenes de compra', icon: 'cart', effect: 'Suma stock al recibir' },
  nota_credito:{ singular: 'Nota de crédito', plural: 'Notas de crédito', icon: 'undo', effect: 'Devuelve stock' },
};

const STATUS = {
  borrador: { label: 'Borrador', tag: 'mute' },
  emitida:  { label: 'Emitida',  tag: 'ok' },
  recibida: { label: 'Recibida', tag: 'terra' },
  anulada:  { label: 'Anulada',  tag: 'bad' },
};

/* ── Datos locales (demo estática) ─────────────────────────────────────── */
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
  const detalle = ruta.match(/^\/api\/documents\/(\d+)$/);
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

/* ── Estado ────────────────────────────────────────────────────────────── */
const state = { user: null, route: 'dashboard', products: [], cache: {} };

/* ── Utilidades de UI ──────────────────────────────────────────────────── */
const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function toast(message, kind = '') {
  const el = $('#toast');
  $('#toast-msg').textContent = message;
  el.className = 'toast' + (kind ? ` toast--${kind}` : '');
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 3200);
}

function openModal({ title, eyebrow = 'Documento', wide = false, body, foot }) {
  $('#modal-eyebrow').textContent = eyebrow;
  $('#modal-title').textContent = title;
  $('#modal-body').innerHTML = body;
  $('#modal-foot').innerHTML = foot || '';
  const modal = $('#modal');
  modal.classList.toggle('modal--wide', !!wide);
  modal.hidden = false;
  const first = $('input, select, textarea, button', $('#modal-body'));
  if (first) first.focus();
  return modal;
}
function closeModal() { $('#modal').hidden = true; }

/* ── Sesión ────────────────────────────────────────────────────────────── */
function showLogin() {
  $('#app').hidden = true;
  $('#view-login').hidden = false;
  state.user = null;
}

function showApp(user) {
  state.user = user;
  $('#view-login').hidden = true;
  $('#app').hidden = false;
  $('#who-name').textContent = user.username;
  $('#who-role').textContent = user.role === 'admin' ? 'Administrador' : 'Vendedor';
  $('#who-avatar').textContent = user.username.charAt(0).toUpperCase();
  navigate('dashboard');
}

async function boot() {
  await esperarDatos;
  showApp(DATOS.me);
  montarAvisoDemo();
}

/* ── Navegación ────────────────────────────────────────────────────────── */
async function navigate(route) {
  state.route = route;
  $$('.navitem').forEach((b) => b.classList.toggle('is-active', b.dataset.route === route));
  $('#content').innerHTML = '<div class="empty">Cargando…</div>';

  if (DOC_LABELS[route]) {
    $('#page-eyebrow').textContent = 'Documentos';
    $('#page-title').textContent = DOC_LABELS[route].plural;
    $('#new-doc-btn').dataset.kind = route;
    $('#new-doc-btn').hidden = false;
    return renderDocuments(route);
  }

  $('#new-doc-btn').hidden = route !== 'inventario';
  $('#new-doc-btn').dataset.kind = 'producto';

  if (route === 'dashboard')    { $('#page-eyebrow').textContent = 'Panel'; $('#page-title').textContent = 'Resumen'; return renderDashboard(); }
  if (route === 'inventario')   { $('#page-eyebrow').textContent = 'Catálogo'; $('#page-title').textContent = 'Inventario'; return renderInventory(); }
  if (route === 'movimientos')  { $('#page-eyebrow').textContent = 'Libro'; $('#page-title').textContent = 'Movimientos de stock'; return renderMovements(); }
}

/* ── Panel ─────────────────────────────────────────────────────────────── */
async function renderDashboard() {
  const [d, docs] = await Promise.all([api('/api/dashboard'), api('/api/documents')]);
  const recent = docs.slice(0, 6);

  $('#content').innerHTML = `
    <div class="grid grid--stats" style="margin-bottom:1.2rem">
      <div class="card stat reveal">
        <p class="stat__label">Vendido</p>
        <p class="stat__value">${money(d.vendido)}</p>
        <p class="stat__foot">${qty(d.n_ventas)} venta${d.n_ventas === 1 ? '' : 's'} emitida${d.n_ventas === 1 ? '' : 's'}</p>
      </div>
      <div class="card stat reveal">
        <p class="stat__label">Valor de stock</p>
        <p class="stat__value">${money(d.stock_value)}</p>
        <p class="stat__foot">a precio de costo</p>
      </div>
      <div class="card stat reveal">
        <p class="stat__label">Productos</p>
        <p class="stat__value">${qty(d.productos)}</p>
        <p class="stat__foot">activos en catálogo</p>
      </div>
      <div class="card stat reveal">
        <p class="stat__label">Por reponer</p>
        <p class="stat__value" style="${d.bajo_stock ? 'color:var(--terra)' : ''}">${qty(d.bajo_stock)}</p>
        <p class="stat__foot">en o bajo el mínimo</p>
      </div>
    </div>

    <div class="grid grid--split">
      <div class="card reveal">
        <div class="card__head">
          <span class="card__title">Actividad reciente</span>
          <button class="card__link" data-goto="venta">Ver ventas</button>
        </div>
        ${recent.length ? `
        <table class="table">
          <thead><tr><th>Documento</th><th>Cliente / Proveedor</th><th>Estado</th><th class="r">Total</th></tr></thead>
          <tbody>
            ${recent.map((doc) => `
              <tr class="doc-row" data-id="${doc.id}">
                <td><span class="strong">${doc.number}</span><br><span class="muted" style="font-size:.8rem">${DOC_LABELS[doc.kind].singular}</span></td>
                <td>${doc.party_name || '<span class="muted">—</span>'}</td>
                <td><span class="tag tag--${(STATUS[doc.status] || {}).tag || 'mute'}">${(STATUS[doc.status] || {}).label || doc.status}</span></td>
                <td class="r strong">${money(doc.total)}</td>
              </tr>`).join('')}
          </tbody>
        </table>` : `<div class="empty"><strong>Sin documentos todavía</strong>Crea una cotización para empezar.</div>`}
      </div>

      <div class="card reveal">
        <div class="card__head"><span class="card__title">Reposición sugerida</span></div>
        ${d.low_stock.length ? `
          <table class="table">
            <thead><tr><th>Producto</th><th class="r">Stock</th><th class="r">Mínimo</th></tr></thead>
            <tbody>${d.low_stock.map((p) => `
              <tr><td>${p.name}<br><span class="muted" style="font-size:.78rem">${p.sku}</span></td>
                  <td class="r qty ${p.stock <= 0 ? 'qty--neg' : ''}">${qty(p.stock)}</td>
                  <td class="r muted">${qty(p.min_stock)}</td></tr>`).join('')}
            </tbody>
          </table>` : `<div class="empty"><strong>Todo con stock suficiente</strong>Nada bajo el mínimo por ahora.</div>`}
      </div>
    </div>`;

  bindDocRows();
  $('[data-goto]', $('#content')).addEventListener('click', (e) => navigate(e.target.dataset.goto));
}

/* ── Inventario ────────────────────────────────────────────────────────── */
async function renderInventory() {
  const products = await api('/api/products');
  state.products = products;

  $('#content').innerHTML = `
    <div class="card reveal" style="padding:0;overflow:hidden">
      ${products.length ? `
      <table class="table">
        <thead><tr>
          <th>Producto</th><th>SKU</th><th class="r">Costo</th><th class="r">Precio</th>
          <th class="r">Margen</th><th class="r">Stock</th><th></th>
        </tr></thead>
        <tbody>
          ${products.map((p) => {
            const margin = p.price_cents ? Math.round((1 - p.cost_cents / p.price_cents) * 100) : null;
            return `<tr>
              <td class="strong">${p.name}${p.low ? ' <span class="tag tag--warn">Reponer</span>' : ''}</td>
              <td class="muted">${p.sku}</td>
              <td class="r num">${money(p.cost)}</td>
              <td class="r num">${money(p.price)}</td>
              <td class="r num ${margin !== null && margin < 0 ? 'qty--neg' : ''}">${margin === null ? '—' : margin + '%'}</td>
              <td class="r qty ${p.stock <= 0 ? 'qty--neg' : ''}">${qty(p.stock)} <span class="muted" style="font-weight:400">${p.unit}</span></td>
              <td class="r"><button class="card__link" data-move="${p.id}">Movimiento</button></td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>` : `<div class="empty"><strong>Catálogo vacío</strong>Agrega tu primer producto para empezar.</div>`}
    </div>`;

  $$('[data-move]', $('#content')).forEach((btn) =>
    btn.addEventListener('click', () => movementModal(Number(btn.dataset.move))));
}

/* ── Movimientos ───────────────────────────────────────────────────────── */
async function renderMovements() {
  const rows = await api('/api/movements');
  $('#content').innerHTML = `
    <div class="card reveal" style="padding:0;overflow:hidden">
      ${rows.length ? `
      <table class="table">
        <thead><tr><th>Fecha</th><th>Producto</th><th>Tipo</th><th class="r">Cantidad</th><th>Referencia</th></tr></thead>
        <tbody>${rows.map((m) => `
          <tr>
            <td class="muted" style="white-space:nowrap">${m.created_at}</td>
            <td>${m.product_name}<br><span class="muted" style="font-size:.78rem">${m.sku}</span></td>
            <td><span class="tag tag--${m.qty >= 0 ? 'ok' : 'bad'}">${m.kind}</span></td>
            <td class="r qty ${m.qty < 0 ? 'qty--neg' : 'qty--pos'}">${m.qty > 0 ? '+' : ''}${qty(m.qty)}</td>
            <td class="muted">${m.note || '—'}</td>
          </tr>`).join('')}
        </tbody>
      </table>` : `<div class="empty"><strong>Sin movimientos</strong>El libro se llena al emitir ventas y recibir compras.</div>`}
    </div>`;
}

/* ── Documentos: listado ───────────────────────────────────────────────── */
async function renderDocuments(kind) {
  const docs = await api(`/api/documents?kind=${kind}`);
  const meta = DOC_LABELS[kind];
  $('#content').innerHTML = `
    <div class="card reveal" style="padding:0;overflow:hidden">
      ${docs.length ? `
      <table class="table table--clickable">
        <thead><tr><th>Número</th><th>${kind === 'orden_compra' ? 'Proveedor' : 'Cliente'}</th>
          <th>Fecha</th><th>Estado</th><th class="r">Total</th></tr></thead>
        <tbody>${docs.map((d) => `
          <tr class="doc-row" data-id="${d.id}">
            <td class="strong">${d.number}</td>
            <td>${d.party_name || '<span class="muted">—</span>'}</td>
            <td class="muted">${d.created_at}</td>
            <td><span class="tag tag--${(STATUS[d.status] || {}).tag || 'mute'}">${(STATUS[d.status] || {}).label || d.status}</span></td>
            <td class="r strong">${money(d.total)}</td>
          </tr>`).join('')}
        </tbody>
      </table>` : `<div class="empty"><strong>Sin ${meta.plural.toLowerCase()}</strong>Crea una con el botón «Nuevo documento».</div>`}
    </div>`;
  bindDocRows();
}

function bindDocRows() {
  $$('.doc-row').forEach((row) => row.addEventListener('click', () => documentModal(Number(row.dataset.id))));
}

/* ── Documentos: detalle ───────────────────────────────────────────────── */
async function documentModal(id) {
  const doc = await api(`/api/documents/${id}`);
  const meta = DOC_LABELS[doc.kind];
  const actions = [];

  if (doc.status === 'borrador') actions.push(`<button class="btn btn--primary" data-act="issue">Emitir</button>`);
  if (doc.kind === 'cotizacion') {
    actions.push(`<button class="btn btn--ghost" data-act="convert" data-target="nota_venta">A nota de venta</button>`);
    actions.push(`<button class="btn btn--ghost" data-act="convert" data-target="venta">A venta</button>`);
  }
  if (doc.kind === 'nota_venta') actions.push(`<button class="btn btn--ghost" data-act="convert" data-target="venta">A venta</button>`);
  if (doc.kind === 'orden_compra' && doc.status === 'emitida') actions.push(`<button class="btn btn--primary" data-act="receive">Recibir mercadería</button>`);
  if (doc.kind === 'venta' && doc.status === 'emitida') actions.push(`<button class="btn btn--danger" data-act="convert" data-target="nota_credito">Nota de crédito</button>`);

  const effect = meta.effect ? `<span class="tag tag--terra">${meta.effect}</span>` : '<span class="muted">Sin efecto en stock</span>';

  openModal({
    eyebrow: meta.singular,
    title: doc.number,
    wide: true,
    body: `
      <div style="display:flex;gap:1rem;flex-wrap:wrap;align-items:center;margin-bottom:1.1rem">
        <span class="tag tag--${(STATUS[doc.status] || {}).tag}">${(STATUS[doc.status] || {}).label}</span>
        ${effect}
        <span class="muted" style="font-size:.82rem">${doc.created_at}</span>
      </div>

      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-bottom:1.2rem">
        <div><p class="eyebrow">${doc.kind === 'orden_compra' ? 'Proveedor' : 'Cliente'}</p><strong>${doc.party_name || '—'}</strong></div>
        <div><p class="eyebrow">RUT / ID</p><strong>${doc.party_tax_id || '—'}</strong></div>
        <div><p class="eyebrow">Dirección</p><strong>${doc.party_address || '—'}</strong></div>
      </div>

      <table class="table">
        <thead><tr><th>Descripción</th><th class="r">Cant.</th><th class="r">P. unitario</th><th class="r">Total</th></tr></thead>
        <tbody>${doc.lines.map((l) => `
          <tr><td>${l.description || '<span class="muted">—</span>'}</td>
              <td class="r qty">${qty(l.qty)}</td>
              <td class="r num">${money(l.unit_price)}</td>
              <td class="r num strong">${money(l.line_total)}</td></tr>`).join('')}
        </tbody>
      </table>

      <div class="totals">
        <div class="totals__row"><span>Neto</span><span>${money(doc.subtotal)}</span></div>
        <div class="totals__row"><span>IVA 19%</span><span>${money(doc.iva)}</span></div>
        <div class="totals__row totals__row--grand"><span>Total</span><span>${money(doc.total)}</span></div>
      </div>

      ${doc.notes ? `<p class="hint" style="margin-top:1.2rem"><b>Notas:</b> ${doc.notes}</p>` : ''}`,
    foot: actions.join('') || '<button class="btn btn--ghost" data-close>Cerrar</button>',
  });

  $$('#modal-foot [data-act]').forEach((btn) => btn.addEventListener('click', async () => {
    const act = btn.dataset.act;
    try {
      if (act === 'issue')    await api(`/api/documents/${id}/issue`, { method: 'POST' });
      if (act === 'receive')  await api(`/api/documents/${id}/receive`, { method: 'POST' });
      if (act === 'convert')  await api(`/api/documents/${id}/convert`, { method: 'POST', body: { target_kind: btn.dataset.target } });
      toast('Listo', 'ok');
      closeModal();
      navigate(state.route);
    } catch (err) { toast(err.message, 'bad'); }
  }));
}

/* ── Documentos: creación ──────────────────────────────────────────────── */
async function newDocumentModal(kind) {
  const meta = DOC_LABELS[kind];
  if (!state.products.length) state.products = await api('/api/products');
  const products = state.products.filter((p) => p.stock > 0 || kind === 'orden_compra');
  const partyLabel = kind === 'orden_compra' ? 'Proveedor' : 'Cliente';

  openModal({
    eyebrow: meta.singular,
    title: `Nueva ${meta.singular.toLowerCase()}`,
    wide: true,
    body: `
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
        <label class="field"><span>${partyLabel}</span><input name="party_name" placeholder="Nombre o razón social"></label>
        <label class="field"><span>RUT / ID</span><input name="party_tax_id" placeholder="12.345.678-9"></label>
      </div>

      <p class="eyebrow" style="margin-top:.6rem">Líneas</p>
      <div class="lines__head"><span>Producto</span><span>Cant.</span><span>P. unitario</span><span>Total</span><span></span></div>
      <div class="lines" id="lines"></div>
      <button class="btn btn--ghost btn--sm" id="add-line">${icon('plus')} Agregar línea</button>

      <label class="field" style="margin-top:1.1rem"><span>Notas</span><textarea name="notes" rows="2" placeholder="Observaciones para el documento"></textarea></label>

      <div class="totals" id="totals"></div>`,
    foot: `<button class="btn btn--ghost" data-close>Cancelar</button>
           <button class="btn btn--primary" id="save-doc">Crear ${meta.singular.toLowerCase()}</button>`,
  });

  const linesEl = $('#lines');
  const addLine = (preset = {}) => {
    const row = document.createElement('div');
    row.className = 'linerow';
    row.innerHTML = `
      <select class="line-product">
        <option value="">— Texto libre —</option>
        ${products.map((p) => `<option value="${p.id}" ${preset.product_id === p.id ? 'selected' : ''}>${p.name} (${p.sku})</option>`).join('')}
      </select>
      <input class="line-qty" type="number" min="1" step="1" value="${preset.qty || 1}">
      <input class="line-price" type="number" min="0" step="1" value="${preset.price || ''}" placeholder="0">
      <span class="linerow__total">$0</span>
      <button class="iconbtn" title="Quitar">${icon('trash')}</button>`;
    linesEl.appendChild(row);

    const sel = $('.line-product', row);
    const qtyIn = $('.line-qty', row);
    const priceIn = $('.line-price', row);

    sel.addEventListener('change', () => {
      const p = products.find((x) => x.id === Number(sel.value));
      if (p) priceIn.value = Math.round(parseFloat(p.price));
      recalc();
    });
    qtyIn.addEventListener('input', recalc);
    priceIn.addEventListener('input', recalc);
    $('.iconbtn', row).addEventListener('click', () => { row.remove(); recalc(); });
    recalc();
  };

  function collect() {
    return $$('.linerow', linesEl).map((row) => {
      const sel = $('.line-product', row);
      const p = products.find((x) => x.id === Number(sel.value));
      return {
        product_id: sel.value ? Number(sel.value) : null,
        description: p ? `${p.name} (${p.sku})` : 'Ítem libre',
        qty: Number($('.line-qty', row).value) || 0,
        unit_price_cents: Math.round((Number($('.line-price', row).value) || 0) * 100),
      };
    });
  }

  function recalc() {
    let total = 0;
    $$('.linerow', linesEl).forEach((row) => {
      const lineTotal = (Number($('.line-qty', row).value) || 0) * (Number($('.line-price', row).value) || 0);
      $('.linerow__total', row).textContent = money(lineTotal);
      total += Math.round(lineTotal * 100);
    });
    const iva = Math.round(total - total / 1.19);
    $('#totals').innerHTML = `
      <div class="totals__row"><span>Neto</span><span>${money((total - iva) / 100)}</span></div>
      <div class="totals__row"><span>IVA 19%</span><span>${money(iva / 100)}</span></div>
      <div class="totals__row totals__row--grand"><span>Total</span><span>${money(total / 100)}</span></div>`;
  }

  $('#add-line').addEventListener('click', () => addLine());
  addLine();

  $('#save-doc').addEventListener('click', async () => {
    const lines = collect();
    if (!lines.length || lines.some((l) => l.qty <= 0)) { toast('Revisa las cantidades', 'bad'); return; }
    try {
      const doc = await api('/api/documents', {
        method: 'POST',
        body: {
          kind,
          lines,
          party_name: $('[name=party_name]').value,
          party_tax_id: $('[name=party_tax_id]').value,
          notes: $('[name=notes]').value,
        },
      });
      toast(`${doc.number} creada`, 'ok');
      closeModal();
      navigate(kind);
      documentModal(doc.id);
    } catch (err) { toast(err.message, 'bad'); }
  });
}

/* ── Selector de tipo de documento ─────────────────────────────────────── */
function newDocumentPicker() {
  openModal({
    eyebrow: 'Nuevo',
    title: '¿Qué documento necesitas?',
    body: `<div class="tilegrid">${Object.entries(DOC_LABELS).map(([kind, meta]) => `
      <button class="tile" data-kind="${kind}">
        <strong>${meta.singular}</strong>
        <small>${kind === 'orden_compra' ? 'Repone stock al recibirla' :
                 kind === 'venta' ? 'Descuenta stock al emitirla' :
                 kind === 'nota_credito' ? 'Devuelve stock al emitirla' :
                 kind === 'cotizacion' ? 'Se convierte en venta' : 'Documento interno de respaldo'}</small>
        <span class="tile__effect tag ${meta.effect ? 'tag--terra' : 'tag--mute'}">${meta.effect || 'Sin efecto en stock'}</span>
      </button>`).join('')}</div>`,
  });
  $$('#modal-body [data-kind]').forEach((btn) => btn.addEventListener('click', () => {
    closeModal();
    if (btn.dataset.kind === 'orden_compra' && state.user.role !== 'admin') {
      toast('Solo un administrador crea órdenes de compra', 'bad'); return;
    }
    newDocumentModal(btn.dataset.kind);
  }));
}

/* ── Producto y movimiento ─────────────────────────────────────────────── */
function productModal() {
  openModal({
    eyebrow: 'Catálogo', title: 'Nuevo producto',
    body: `
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr))">
        <label class="field"><span>SKU</span><input name="sku" required placeholder="P-001"></label>
        <label class="field"><span>Nombre</span><input name="name" required placeholder="Cemento 25 kg"></label>
        <label class="field"><span>Unidad</span><input name="unit" value="un"></label>
        <label class="field"><span>Stock mínimo</span><input name="min_stock" type="number" min="0" value="0"></label>
        <label class="field"><span>Costo</span><input name="cost" type="number" min="0" step="1" value="0"></label>
        <label class="field"><span>Precio</span><input name="price" type="number" min="0" step="1" value="0"></label>
      </div>`,
    foot: `<button class="btn btn--ghost" data-close>Cancelar</button>
           <button class="btn btn--primary" id="save-product">Guardar</button>`,
  });
  $('#save-product').addEventListener('click', async () => {
    try {
      await api('/api/products', { method: 'POST', body: {
        sku: $('[name=sku]').value, name: $('[name=name]').value, unit: $('[name=unit]').value || 'un',
        min_stock: Number($('[name=min_stock]').value) || 0,
        cost_cents: Math.round((Number($('[name=cost]').value) || 0) * 100),
        price_cents: Math.round((Number($('[name=price]').value) || 0) * 100),
      }});
      toast('Producto agregado', 'ok');
      closeModal();
      navigate('inventario');
    } catch (err) { toast(err.message, 'bad'); }
  });
}

async function movementModal(productId) {
  if (!state.products.length) state.products = await api('/api/products');
  const p = state.products.find((x) => x.id === productId);
  openModal({
    eyebrow: 'Libro de stock', title: `Movimiento · ${p ? p.name : ''}`,
    body: `
      <p class="hint" style="margin-top:0">Stock actual: <b>${qty(p ? p.stock : 0)} ${p ? p.unit : ''}</b></p>
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr))">
        <label class="field"><span>Tipo</span><select name="kind">
          <option value="entrada">Entrada (suma)</option>
          <option value="salida">Salida (resta)</option>
          <option value="ajuste">Ajuste (fija)</option>
        </select></label>
        <label class="field"><span>Cantidad</span><input name="qty" type="number" min="1" value="1"></label>
      </div>
      <label class="field"><span>Nota</span><input name="note" placeholder="Motivo del movimiento"></label>`,
    foot: `<button class="btn btn--ghost" data-close>Cancelar</button>
           <button class="btn btn--primary" id="save-move">Registrar</button>`,
  });
  $('#save-move').addEventListener('click', async () => {
    const kind = $('[name=kind]').value;
    const n = Number($('[name=qty]').value) || 0;
    if (n <= 0) { toast('Cantidad inválida', 'bad'); return; }
    const signed = kind === 'entrada' ? n : kind === 'salida' ? -n : n - (p ? p.stock : 0);
    try {
      await api('/api/movements', { method: 'POST', body: {
        product_id: productId, qty: signed, kind: kind === 'ajuste' ? 'ajuste' : kind,
        note: $('[name=note]').value || 'Ajuste manual',
      }});
      toast('Movimiento registrado', 'ok');
      closeModal();
      navigate('inventario');
    } catch (err) { toast(err.message, 'bad'); }
  });
}

/* ── Arranque y eventos ────────────────────────────────────────────────── */
function wire() {
  $$('.navitem').forEach((b) => {
    const mark = $('i[data-icon]', b);
    if (mark) mark.innerHTML = icon(mark.dataset.icon);
    b.addEventListener('click', () => navigate(b.dataset.route));
  });

  $('#new-doc-btn').addEventListener('click', () => {
    const kind = $('#new-doc-btn').dataset.kind;
    if (kind === 'producto') productModal();
    else if (kind && DOC_LABELS[kind]) newDocumentModal(kind);
    else newDocumentPicker();
  });

  $('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    try {
      showApp(await api('/api/auth/login', { method: 'POST', body: {
        username: form.get('username'), password: form.get('password'),
      }}));
    } catch (err) { toast(err.message, 'bad'); }
  });

  $('#logout').addEventListener('click', async () => {
    await api('/api/auth/logout', { method: 'POST' });
    showLogin();
  });

  $('#modal').addEventListener('click', (e) => { if (e.target.closest('[data-close]')) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
}

$('#sidebar-icons')?.remove();
wire();
boot();
