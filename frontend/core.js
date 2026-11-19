/* =====================================================================
   Boletería · núcleo: API, sesión, router, utilidades, pósters, modales
   ===================================================================== */
"use strict";

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

// ---------- almacenamiento (puede fallar en modo privado) ----------
const memoria = {};
const guardar = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { memoria[k] = v; } };
const leer = (k) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : memoria[k] ?? null; } catch { return memoria[k] ?? null; } };
const borrar = (k) => { try { localStorage.removeItem(k); } catch { /* nada */ } delete memoria[k]; };

const estado = { token: leer("token"), sesion: leer("sesion"), perfil: leer("perfil"), timers: [] };
const esAdmin = () => estado.sesion?.rol === "administrador";

// ---------- escape HTML (los datos vienen de usuarios/administradores) ----------
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- API ----------
class ErrorApi extends Error {
  constructor(status, detalle) { super(textoError(detalle)); this.status = status; this.detalle = detalle; }
}
function textoError(d) {
  if (!d) return "Ocurrió un error inesperado";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => (e.msg || "").replace(/^Value error, /, "")).join(". ");
  if (d.mensaje) return d.mensaje;
  return JSON.stringify(d);
}
async function api(servicio, ruta, { metodo = "GET", cuerpo, silencioso = false } = {}) {
  const headers = { Accept: "application/json" };
  if (cuerpo !== undefined) headers["Content-Type"] = "application/json";
  if (estado.token) headers.Authorization = `Bearer ${estado.token}`;
  let r;
  try {
    r = await fetch(`/api/${servicio}${ruta}`, { method: metodo, headers, body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined });
  } catch {
    throw new ErrorApi(0, "No hay conexión con el servidor");
  }
  let datos = null;
  if (r.status !== 204) { try { datos = await r.json(); } catch { datos = null; } }
  if (!r.ok) {
    if (r.status === 401 && estado.token && !silencioso && servicio !== "acceso") {
      cerrarSesionLocal();
      toast("Tu sesión expiró. Inicia sesión de nuevo.", "info");
      navegar("/login");
    }
    throw new ErrorApi(r.status, datos?.detail ?? `Error ${r.status}`);
  }
  return datos;
}

// ---------- formato ----------
const fmtCOP = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
const moneda = (v) => fmtCOP.format(Number(v || 0));
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const MESES_L = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
function fechaEvento(ev) {           // fecha y hora locales del evento (no se convierten de zona)
  const [a, m, d] = ev.fecha.split("-").map(Number);
  const [h, mi] = (ev.hora || "00:00").split(":").map(Number);
  return new Date(a, m - 1, d, h, mi);
}
const fmtFechaLarga = (dt) => dt.toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const fmtFechaCorta = (dt) => dt.toLocaleDateString("es-CO", { weekday: "short", day: "numeric", month: "short" });
const fmtHora = (dt) => dt.toLocaleTimeString("es-CO", { hour: "numeric", minute: "2-digit" });
const utc = (s) => (s ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(s) ? s : `${s}Z`) : null);  // el backend guarda UTC
const fmtFechaHora = (s) => { const d = utc(s); return d ? d.toLocaleString("es-CO", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "—"; };
function haceCuanto(s) {
  const d = utc(s); if (!d) return "";
  const seg = Math.round((Date.now() - d) / 1000);
  if (seg < 60) return "hace un momento";
  if (seg < 3600) return `hace ${Math.floor(seg / 60)} min`;
  if (seg < 86400) return `hace ${Math.floor(seg / 3600)} h`;
  return d.toLocaleDateString("es-CO", { day: "numeric", month: "short" });
}
const mmss = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
const iniciales = (n, a) => `${(n || "?")[0]}${(a || "")[0] || ""}`.toUpperCase();

// ---------- toasts ----------
function toast(mensaje, tipo = "ok", ms = 4200) {
  const iconos = { ok: "✓", error: "!", info: "ℹ" };
  const t = document.createElement("div");
  t.className = `toast ${tipo}`;
  t.innerHTML = `<b>${iconos[tipo] || ""}</b><span>${esc(mensaje)}</span>`;
  $("#toasts").appendChild(t);
  setTimeout(() => { t.classList.add("saliendo"); setTimeout(() => t.remove(), 300); }, ms);
}
const toastError = (e) => toast(e?.message || String(e), "error", 6000);

// ---------- modales ----------
function modal(titulo, html, { ancho = false, alCerrar } = {}) {
  const fondo = document.createElement("div");
  fondo.className = "modal-fondo";
  fondo.innerHTML = `<div class="modal ${ancho ? "ancho" : ""}" role="dialog" aria-modal="true">
      <div class="modal-cab"><h3>${titulo}</h3><button class="cerrar" aria-label="Cerrar">✕</button></div>
      <div class="modal-cuerpo">${html}</div></div>`;
  const cerrar = () => { fondo.remove(); document.removeEventListener("keydown", tecla); alCerrar?.(); };
  const tecla = (e) => { if (e.key === "Escape") cerrar(); };
  fondo.addEventListener("mousedown", (e) => { if (e.target === fondo) cerrar(); });
  $(".cerrar", fondo).onclick = cerrar;
  document.addEventListener("keydown", tecla);
  $("#modal-raiz").appendChild(fondo);
  setTimeout(() => $("input, select, textarea", fondo)?.focus(), 50);
  return { el: $(".modal-cuerpo", fondo), cerrar, titulo: (t) => ($(".modal-cab h3", fondo).innerHTML = t) };
}
function confirmar(texto, { si = "Confirmar", peligro = false } = {}) {
  return new Promise((ok) => {
    let decidido = false;
    const m = modal("¿Estás seguro?", `<p style="margin:0 0 20px;color:var(--suave)">${texto}</p>
      <div style="display:flex;gap:10px;justify-content:flex-end"><button class="btn btn-fantasma" data-no>Volver</button>
      <button class="btn ${peligro ? "btn-peligro" : "btn-primario"}" data-si>${si}</button></div>`,
    { alCerrar: () => { if (!decidido) ok(false); } });
    $("[data-no]", m.el).onclick = () => m.cerrar();
    $("[data-si]", m.el).onclick = () => { decidido = true; m.cerrar(); ok(true); };
  });
}
/** Maneja un formulario: deshabilita el botón mientras se envía y muestra errores. */
function alEnviar(form, fn) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("button[type=submit]", form);
    const txt = btn?.innerHTML;
    if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spinner" style="width:16px;height:16px;border-width:2px"></span>`; }
    try { await fn(Object.fromEntries(new FormData(form))); }
    catch (err) { toastError(err); }
    finally { if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = txt; } }
  });
}
function confeti() {
  const c = document.createElement("div"); c.className = "confeti";
  const colores = ["#1f4fa3", "#0f766e", "#e0a54a", "#9fb3d9", "#6b4fa0"];
  for (let i = 0; i < 90; i++) {
    const p = document.createElement("i");
    p.style.left = `${Math.random() * 100}%`;
    p.style.background = colores[i % colores.length];
    p.style.animationDuration = `${1.8 + Math.random() * 1.8}s`;
    p.style.animationDelay = `${Math.random() * .5}s`;
    p.style.transform = `rotate(${Math.random() * 360}deg)`;
    c.appendChild(p);
  }
  document.body.appendChild(c);
  setTimeout(() => c.remove(), 4200);
}

// ---------- pósters generados (sin imágenes externas) ----------
const GENEROS = [
  { k: /cumbia|vallenato|salsa|tropical|merengue|champeta|porro/i, n: "Tropical", f: "ondas" },
  { k: /rock|metal|punk|banda/i, n: "Rock", f: "rayos" },
  { k: /electr|dj|techno|house|festival/i, n: "Electrónica", f: "rejilla" },
  { k: /sinf|orquesta|filarm|clásic|ópera|opera/i, n: "Clásica", f: "arcos" },
  { k: /jazz|blues|soul/i, n: "Jazz", f: "arcos" },
  { k: /comedia|stand.?up|risa|humor/i, n: "Comedia", f: "puntos" },
  { k: /teatro|obra|musical/i, n: "Teatro", f: "arcos" },
  { k: /concierto|gira|tour|en vivo/i, n: "Concierto", f: "rayos" },
];
const PALETAS = [
  ["#e8b04b", "#f3e7d3", "#1f3a5f"], ["#7fb8b0", "#e6efe9", "#173f3a"], ["#d98f7a", "#f4e4dc", "#4a2330"],
  ["#9fb3d9", "#e7ecf6", "#26324d"], ["#d6b36a", "#f1e8d2", "#3d3424"], ["#b7a3d6", "#ece6f5", "#2f2a48"],
  ["#8fc1d4", "#e4f1f6", "#183b4a"], ["#e0a370", "#f6e9dc", "#3b2a20"],
];
function hash(s) { let h = 2166136261; for (const c of String(s)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
function genero(ev) { const t = `${ev.nombre} ${ev.descripcion || ""}`; return GENEROS.find((g) => g.k.test(t)) || { n: "Evento", f: "puntos" }; }
function arteSVG(ev) {
  const h = hash(ev.nombre + ev.id_evento);
  const [c1, c2, fondo] = PALETAS[h % PALETAS.length];
  const g = genero(ev);
  const id = `g${ev.id_evento}${h % 997}`;
  const r = (n) => ((h >> (n % 24)) % 100) / 100;
  let figuras = "";
  if (g.f === "ondas") {
    for (let i = 0; i < 7; i++) {
      const y = 150 + i * 32;
      figuras += `<path d="M-20 ${y} Q 75 ${y - 50 - r(i) * 40} 150 ${y} T 320 ${y}" fill="none" stroke="${i % 2 ? c1 : c2}" stroke-width="${8 - i * .7}" opacity="${.85 - i * .09}"/>`;
    }
    figuras += `<circle cx="${210 + r(3) * 40}" cy="95" r="54" fill="${c1}" opacity=".85"/>`;
  } else if (g.f === "rayos") {
    for (let i = 0; i < 9; i++) {
      const x = 150 + Math.cos(i * 0.7 + r(1)) * 40;
      figuras += `<polygon points="${x},${-20} ${x + 26},${-20} ${150 + (i - 4) * 60},420 ${150 + (i - 4) * 60 - 8},420" fill="${i % 2 ? c1 : c2}" opacity="${.22 + (i % 3) * .1}"/>`;
    }
    figuras += `<polygon points="150,70 190,170 160,170 185,260 115,150 145,150 120,70" fill="${c1}" opacity=".9"/>`;
  } else if (g.f === "rejilla") {
    for (let i = 0; i < 14; i++) figuras += `<line x1="${-100 + i * 36}" y1="400" x2="150" y2="210" stroke="${c2}" stroke-width="1.5" opacity=".55"/>`;
    for (let i = 0; i < 7; i++) figuras += `<line x1="0" y1="${230 + i * i * 4}" x2="300" y2="${230 + i * i * 4}" stroke="${c1}" stroke-width="1.5" opacity="${.3 + i * .08}"/>`;
    figuras += `<circle cx="150" cy="150" r="70" fill="none" stroke="${c1}" stroke-width="10" opacity=".9"/><circle cx="150" cy="150" r="42" fill="${c2}" opacity=".7"/>`;
  } else if (g.f === "arcos") {
    for (let i = 0; i < 6; i++) figuras += `<circle cx="${80 + r(2) * 140}" cy="380" r="${60 + i * 38}" fill="none" stroke="${i % 2 ? c1 : c2}" stroke-width="${3 + (i % 3) * 3}" opacity="${.8 - i * .1}"/>`;
    figuras += `<circle cx="${220 - r(5) * 60}" cy="90" r="34" fill="${c2}" opacity=".9"/>`;
  } else {
    for (let i = 0; i < 40; i++) {
      const x = (h * (i + 3)) % 300, y = (h * (i + 7) * 13) % 400;
      figuras += `<circle cx="${x}" cy="${y}" r="${4 + (i % 5) * 4}" fill="${i % 2 ? c1 : c2}" opacity="${.25 + (i % 4) * .15}"/>`;
    }
  }
  return `<svg class="arte" viewBox="0 0 300 400" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${fondo}"/><stop offset="1" stop-color="${c1}" stop-opacity=".28"/></linearGradient>
    <linearGradient id="${id}s" x1="0" y1="0" x2="0" y2="1"><stop offset=".45" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".55"/></linearGradient></defs>
    <rect width="300" height="400" fill="url(#${id})"/>${figuras}<rect width="300" height="400" fill="url(#${id}s)"/></svg>`;
}
function poster(ev, { titulo = true, clase = "" } = {}) {
  const g = genero(ev);
  const foto = ev.imagen ? `<img class="foto" src="${esc(ev.imagen)}" alt="" loading="lazy">` : arteSVG(ev);
  const aviso = ev.estado === "aplazado" ? `<span class="p-aplazado">Aplazado</span>` : "";
  return `<div class="poster ${ev.imagen ? "con-foto" : ""} ${clase}">${foto}<span class="p-genero">${g.n}</span>${aviso}${titulo ? `<div class="p-titulo">${esc(ev.nombre)}</div>` : ""}</div>`;
}
const EN_VENTA = ["programado", "aplazado"];
const ETIQUETA_ESTADO = { programado: "Programado", aplazado: "Aplazado", realizado: "Realizado", cancelado: "Cancelado" };
const chipEstado = (e) => `<span class="estado e-${e}">${ETIQUETA_ESTADO[e] || e}</span>`;

/** Reduce la imagen en el navegador (máx. 1400 px, JPEG) antes de subirla. */
function imagenADataURL(archivo, max = 1400) {
  return new Promise((ok, mal) => {
    if (!/^image\/(jpeg|png|webp)$/.test(archivo.type)) return mal(new Error("Usa una imagen JPG, PNG o WEBP"));
    const lector = new FileReader();
    lector.onerror = () => mal(new Error("No se pudo leer la imagen"));
    lector.onload = () => {
      const img = new Image();
      img.onerror = () => mal(new Error("La imagen está dañada"));
      img.onload = () => {
        const k = Math.min(1, max / Math.max(img.width, img.height));
        const c = document.createElement("canvas");
        c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
        const ctx = c.getContext("2d");
        ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);
        ctx.drawImage(img, 0, 0, c.width, c.height);
        ok(c.toDataURL("image/jpeg", 0.85));
      };
      img.src = lector.result;
    };
    lector.readAsDataURL(archivo);
  });
}

// ---------- intervalos ligados a la vista actual ----------
function cadaTanto(fn, ms) { const id = setInterval(fn, ms); estado.timers.push(id); return id; }
function limpiarTimers() { estado.timers.forEach(clearInterval); estado.timers = []; }

// ---------- router ----------
const rutas = [];
function ruta(patron, vista, { admin = false, publica = false } = {}) {
  const claves = [];
  const re = new RegExp("^" + patron.replace(/:(\w+)/g, (_, k) => { claves.push(k); return "([^/]+)"; }) + "$");
  rutas.push({ re, claves, vista, admin, publica });
}
function navegar(r) { if (location.hash !== `#${r}`) location.hash = r; else render(); }
async function render() {
  limpiarTimers();
  $("#notif-panel").innerHTML = "";
  const actual = location.hash.slice(1) || (estado.token ? "/catalogo" : "/login");
  for (const r of rutas) {
    const m = actual.match(r.re);
    if (!m) continue;
    if (!r.publica && !estado.token) return navegar("/login");
    if (r.publica && estado.token && actual === "/login") return navegar("/catalogo");
    if (r.admin && !esAdmin()) { toast("Esa sección es solo para administradores", "error"); return navegar("/catalogo"); }
    const params = Object.fromEntries(r.claves.map((k, i) => [k, decodeURIComponent(m[i + 1])]));
    pintarBarra(actual);
    const app = $("#app");
    app.innerHTML = `<main><div class="cargando"><div class="spinner"></div></div></main>`;
    window.scrollTo({ top: 0 });
    try { await r.vista(app, params); }
    catch (e) { app.innerHTML = `<main><div class="vacio"><div class="grande">⚠️</div><h3>No se pudo cargar</h3><p>${esc(e.message)}</p><button class="btn btn-sec" onclick="render()">Reintentar</button></div></main>`; }
    return;
  }
  navegar(estado.token ? "/catalogo" : "/login");
}
window.addEventListener("hashchange", render);

// ---------- barra superior ----------
function pintarBarra(actual) {
  const conSesion = !!estado.token;
  $("#topbar").hidden = !conSesion;
  $("#pie").hidden = !conSesion;
  if (!conSesion) return;
  const enlaces = [["/catalogo", "Catálogo"], ["/reservas", "Mis reservas"], ["/boletas", "Mis boletas"], ["/historial", "Historial"]];
  if (esAdmin()) enlaces.push(["/admin", "⚙ Administración"]);
  $("#nav").innerHTML = enlaces.map(([h, t]) =>
    `<a href="#${h}" class="${actual.startsWith(h) || (h === "/catalogo" && actual.startsWith("/evento")) ? "activo" : ""} ${h === "/admin" ? "admin-link" : ""}">${t}</a>`).join("");
  const p = estado.perfil;
  $("#avatar").textContent = p ? iniciales(p.nombre, p.apellido) : "?";
  $("#nombre-u").textContent = p ? `${p.nombre}${esAdmin() ? " · admin" : ""}` : "";
  pintarCreditos();
}
function pintarCreditos() {
  const c = $("#creditos-chip");
  c.hidden = !estado.saldo;
  c.innerHTML = `<span>Créditos</span><b>${moneda(estado.saldo || 0)}</b>`;
}
async function revisarCreditos() {
  if (!estado.token) return;
  try { estado.saldo = (await api("pagos", "/creditos/mis", { silencioso: true })).saldo; pintarCreditos(); } catch { /* sin cambios */ }
}
$("#btn-usuario").onclick = () => navegar("/perfil");
$("#btn-salir").onclick = async () => {
  try { await api("acceso", "/auth/logout", { metodo: "POST", silencioso: true }); } catch { /* ya expirada */ }
  cerrarSesionLocal();
  toast("Sesión cerrada", "info");
  navegar("/login");
};

// ---------- sesión ----------
async function iniciarSesion(correo, contrasena) {
  const t = await api("acceso", "/auth/login", { metodo: "POST", cuerpo: { correo, contrasena } });
  estado.token = t.access_token;
  estado.sesion = await api("acceso", "/auth/me");
  estado.perfil = await api("usuarios", "/usuarios/me");
  guardar("token", estado.token); guardar("sesion", estado.sesion); guardar("perfil", estado.perfil);
  ultimoPendientes = -1;
  revisarNotificaciones();
  revisarCreditos();
}
function cerrarSesionLocal() {
  estado.token = estado.sesion = estado.perfil = null;
  estado.saldo = 0;
  borrar("token"); borrar("sesion"); borrar("perfil");
  $("#notif-badge").hidden = true;
}

// ---------- notificaciones (RF-NOT) ----------
const ICONO_NOTIF = { reserva: "⏳", pago: "🎟", expiracion: "⌛", evento: "📅", credito: "💳" };
let ultimoPendientes = -1;
async function revisarNotificaciones(abrir = false, silenciar = false) {
  if (!estado.token) return;
  let datos;
  try { datos = await api("notificaciones", "/notificaciones/mis", { silencioso: true }); } catch { return; }
  const b = $("#notif-badge");
  b.hidden = !datos.pendientes; b.textContent = datos.pendientes > 9 ? "9+" : datos.pendientes;
  if (datos.items.some((n) => n.tipo === "credito" && n.estado === "pendiente")) revisarCreditos();
  if (!silenciar && ultimoPendientes >= 0 && datos.pendientes > ultimoPendientes && datos.items[0]) toast(datos.items[0].mensaje, "info");
  ultimoPendientes = datos.pendientes;
  if (!abrir) return;
  $("#notif-panel").innerHTML = `<div class="notif-panel"><header>Notificaciones <a href="#/historial" style="font-size:.8rem;color:var(--suave)">Ver historial</a></header>
    <div class="notif-lista">${datos.items.length ? datos.items.map((n) => `
      <div class="notif ${n.estado === "pendiente" ? "nueva" : ""}"><div class="ni ${n.tipo}">${ICONO_NOTIF[n.tipo]}</div>
      <div>${esc(n.mensaje)}<small>${n.estado === "pendiente" ? "Nueva" : `Entregada ${haceCuanto(n.fecha_envio)}`}</small></div></div>`).join("")
    : `<div class="vacio" style="border:0">Sin notificaciones todavía</div>`}</div></div>`;
  if (datos.pendientes) {
    await api("notificaciones", "/notificaciones/marcar-enviadas", { metodo: "POST", silencioso: true }).catch(() => {});
    b.hidden = true; ultimoPendientes = 0;
  }
}
$("#btn-notif").onclick = (e) => {
  e.stopPropagation();
  if ($("#notif-panel").innerHTML) { $("#notif-panel").innerHTML = ""; return; }
  revisarNotificaciones(true);
};
document.addEventListener("click", (e) => { if (!e.target.closest("#notif-panel")) $("#notif-panel").innerHTML = ""; });
setInterval(() => { revisarNotificaciones(false); revisarCreditos(); }, 20000);

const ICONOS = {
  lugar: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>`,
  buscar: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`,
  flecha: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 12h14M13 5l7 7-7 7"/></svg>`,
  atras: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>`,
};
