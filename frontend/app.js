/* =====================================================================
   Boletería · vistas del usuario
   ===================================================================== */
"use strict";

const ZONA_COLORES = ["#1f4fa3", "#0f766e", "#b45309", "#6b4fa0", "#9f1239", "#0369a1", "#4d7c0f"];

// =====================================================================
// LOGIN / REGISTRO (CU-01, CU-03)
// =====================================================================
ruta("/login", async (app) => {
  const muestras = [
    { id_evento: 1, nombre: "Noche de Cumbia", descripcion: "cumbia" },
    { id_evento: 2, nombre: "Rock en vivo", descripcion: "rock" },
    { id_evento: 3, nombre: "Festival Electrónico", descripcion: "electrónica" },
  ];
  app.innerHTML = `
  <div class="login-wrap">
    <section class="login-hero fade-in">
      <div class="logo" style="margin-bottom:28px"><span class="marca"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2"><path d="M3 8a2 2 0 0 0 2-2h14a2 2 0 0 0 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 0-2 2H5a2 2 0 0 0-2-2v-2a2 2 0 0 0 0-4z"/></svg></span><span>BOLETER<b>Í</b>A</span></div>
      <h1>Tu asiento, <em>asegurado</em> de verdad.</h1>
      <p>Explora conciertos y eventos, elige tu asiento en el mapa en tiempo real y recibe tu boleta con código QR. Cada asiento se vende una sola vez por evento.</p>
      <div class="collage">${muestras.map((m) => `<div class="mini">${poster(m)}</div>`).join("")}</div>
    </section>
    <section class="panel login-card fade-in">
      <div class="tabs"><button class="activo" data-tab="login">Iniciar sesión</button><button data-tab="registro">Crear cuenta</button></div>
      <div id="tab-cuerpo"></div>
    </section>
  </div>`;
  const pintar = (tab) => {
    $$(".tabs button", app).forEach((b) => b.classList.toggle("activo", b.dataset.tab === tab));
    const c = $("#tab-cuerpo", app);
    if (tab === "login") {
      c.innerHTML = `<form class="form" id="f-login">
        <label class="campo">Correo electrónico<input name="correo" type="email" required autocomplete="email" placeholder="tu@correo.com"></label>
        <label class="campo">Contraseña<input name="contrasena" type="password" required autocomplete="current-password" placeholder="••••••••"></label>
        <button class="btn btn-primario btn-xl" type="submit">Entrar</button></form>
        <div class="demo-cuentas"><p>Cuentas de demostración</p><div class="fila-2">
          <button class="btn btn-sec" data-demo="usuario">👤 Usuario<small>usuario@boleteria.com</small></button>
          <button class="btn btn-sec" data-demo="admin">⚙ Administrador<small>admin@boleteria.com</small></button></div></div>`;
      alEnviar($("#f-login", c), async (d) => {
        await iniciarSesion(d.correo, d.contrasena);
        toast(`¡Hola, ${estado.perfil.nombre}!`);
        navegar("/catalogo");
      });
      $$("[data-demo]", c).forEach((b) => b.onclick = () => {
        const f = $("#f-login", c);
        f.correo.value = b.dataset.demo === "admin" ? "admin@boleteria.com" : "usuario@boleteria.com";
        f.contrasena.value = b.dataset.demo === "admin" ? "Admin12345" : "Usuario12345";
        f.requestSubmit();
      });
    } else {
      c.innerHTML = `<form class="form" id="f-reg">
        <div class="fila-2"><label class="campo">Nombre<input name="nombre" required maxlength="80"></label>
        <label class="campo">Apellido<input name="apellido" required maxlength="80"></label></div>
        <label class="campo">Correo electrónico<input name="correo" type="email" required maxlength="120"></label>
        <div class="fila-2"><label class="campo">Teléfono<input name="telefono" required pattern="\\+?[0-9 ]{7,20}" placeholder="3001234567"></label>
        <label class="campo">Documento<input name="documento" required pattern="[A-Za-z0-9]{5,20}" placeholder="1012345678"></label></div>
        <label class="campo">Contraseña<input name="contrasena" type="password" required minlength="8" autocomplete="new-password">
          <span class="ayuda">Mínimo 8 caracteres, con al menos una letra y un número.</span></label>
        <button class="btn btn-primario btn-xl" type="submit">Crear mi cuenta</button></form>`;
      alEnviar($("#f-reg", c), async (d) => {
        await api("usuarios", "/usuarios/registro", { metodo: "POST", cuerpo: d });
        await iniciarSesion(d.correo, d.contrasena);
        toast("¡Cuenta creada! Bienvenido a Boletería");
        navegar("/catalogo");
      });
    }
  };
  $$(".tabs button", app).forEach((b) => b.onclick = () => pintar(b.dataset.tab));
  pintar("login");
}, { publica: true });

// =====================================================================
// CATÁLOGO INTERACTIVO (RF-EVE-03, RF-DIS-02)
// =====================================================================
ruta("/catalogo", async (app) => {
  const [eventos, escenarios] = await Promise.all([
    api("eventos", "/eventos"), api("escenarios", "/escenarios")]);
  const resumen = eventos.length
    ? await api("disponibilidad", `/disponibilidad/resumen?eventos_ids=${eventos.map((e) => e.id_evento).join(",")}`) : [];
  const disp = Object.fromEntries(resumen.map((r) => [r.id_evento, r]));
  const meses = [...new Set(eventos.map((e) => e.fecha.slice(0, 7)))];
  const generos = [...new Set(eventos.map((e) => genero(e).n))];
  const f = { q: "", escenario: "", mes: "", genero: "", precio: "", orden: "fecha", soloDisp: false };

  app.innerHTML = `<main>
    <div id="destacado"></div>
    <div class="titulo-seccion"><div><h1>Próximos eventos</h1><p>${eventos.length} evento(s) con boletas a la venta</p></div></div>
    <div class="filtros">
      <div class="buscar">${ICONOS.buscar}<input id="f-q" placeholder="Busca por artista, género o evento…" autocomplete="off"></div>
      <select id="f-esc"><option value="">Todos los escenarios</option>${escenarios.map((e) => `<option value="${e.id_escenario}">${esc(e.nombre)}</option>`).join("")}</select>
      <select id="f-precio"><option value="">Cualquier precio</option><option value="100000">Desde menos de $100.000</option><option value="150000">Desde menos de $150.000</option><option value="250000">Desde menos de $250.000</option></select>
      <select id="f-orden"><option value="fecha">Más próximos</option><option value="precio">Menor precio</option><option value="disp">Más disponibilidad</option><option value="vendidos">Más vendidos</option></select>
    </div>
    <div class="chips-mes" id="chips">
      <button class="chip btn-chip on" data-mes="">Todas las fechas</button>
      ${meses.map((m) => { const [a, mm] = m.split("-"); return `<button class="chip btn-chip" data-mes="${m}">${MESES_L[+mm - 1]} ${a}</button>`; }).join("")}
      <span style="width:12px"></span>
      ${generos.map((g) => `<button class="chip btn-chip" data-gen="${g}">${g}</button>`).join("")}
      <span class="sep"></span>
      <label class="chip btn-chip" style="cursor:pointer"><input type="checkbox" id="f-disp" style="width:auto;margin:0"> Solo con boletas disponibles</label>
    </div>
    <div class="grid-eventos" id="grid"></div></main>`;

  // ---- destacado con cuenta regresiva ----
  const top = eventos.slice(0, 4);
  let idx = 0;
  const pintarDestacado = () => {
    const ev = top[idx]; if (!ev) { $("#destacado").innerHTML = ""; return; }
    const d = disp[ev.id_evento] || {};
    $("#destacado").innerHTML = `<section class="destacado fade-in">
      <div class="d-info"><span class="etq">★ Destacado · ${genero(ev).n}</span><h2>${esc(ev.nombre)}</h2>
        <div class="d-meta"><span>📅 ${fmtFechaLarga(fechaEvento(ev))}</span><span>🕗 ${fmtHora(fechaEvento(ev))}</span><span>📍 ${esc(ev.escenario?.nombre || "")}</span></div>
        <div class="cuenta" id="cuenta"></div>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap"><a class="btn btn-primario" href="#/evento/${ev.id_evento}">Elegir asientos ${ICONOS.flecha}</a>
        ${d.precio_desde != null ? `<span style="color:var(--suave)">desde <b style="color:var(--oro);font-family:var(--display);font-size:1.15rem">${moneda(d.precio_desde)}</b></span>` : ""}</div></div>
      ${poster(ev, { titulo: false })}
      <div class="d-puntos">${top.map((_, i) => `<button class="${i === idx ? "on" : ""}" data-i="${i}" aria-label="Destacado ${i + 1}"></button>`).join("")}</div></section>`;
    $$(".d-puntos button").forEach((b) => b.onclick = () => { idx = +b.dataset.i; pintarDestacado(); });
    tic();
  };
  const tic = () => {
    const ev = top[idx]; const c = $("#cuenta"); if (!ev || !c) return;
    let s = Math.max(0, Math.floor((fechaEvento(ev) - Date.now()) / 1000));
    const p = [[Math.floor(s / 86400), "días"], [Math.floor(s % 86400 / 3600), "horas"], [Math.floor(s % 3600 / 60), "min"], [s % 60, "seg"]];
    c.innerHTML = p.map(([v, t]) => `<div><b>${String(v).padStart(2, "0")}</b><small>${t}</small></div>`).join("");
  };
  pintarDestacado();
  cadaTanto(tic, 1000);
  cadaTanto(() => { if (top.length > 1) { idx = (idx + 1) % top.length; pintarDestacado(); } }, 7000);

  // ---- grilla filtrable ----
  const pintarGrid = () => {
    const q = f.q.toLowerCase();
    let lista = eventos.filter((e) => {
      const d = disp[e.id_evento] || {};
      return (!q || `${e.nombre} ${e.descripcion || ""} ${e.escenario?.nombre || ""} ${genero(e).n}`.toLowerCase().includes(q))
        && (!f.escenario || e.id_escenario === +f.escenario)
        && (!f.mes || e.fecha.startsWith(f.mes))
        && (!f.genero || genero(e).n === f.genero)
        && (!f.precio || (d.precio_desde ?? Infinity) < +f.precio)
        && (!f.soloDisp || d.disponible > 0);
    });
    const orden = {
      fecha: (a, b) => fechaEvento(a) - fechaEvento(b),
      precio: (a, b) => (disp[a.id_evento]?.precio_desde ?? 1e12) - (disp[b.id_evento]?.precio_desde ?? 1e12),
      disp: (a, b) => (disp[b.id_evento]?.disponible || 0) - (disp[a.id_evento]?.disponible || 0),
      vendidos: (a, b) => (disp[b.id_evento]?.vendido || 0) - (disp[a.id_evento]?.vendido || 0),
    }[f.orden];
    lista = lista.sort(orden);
    const g = $("#grid");
    if (!lista.length) {
      g.innerHTML = `<div class="vacio" style="grid-column:1/-1"><div class="grande">🔍</div><h3>Ningún evento coincide</h3><p>Prueba con otros filtros.</p></div>`;
      return;
    }
    g.innerHTML = lista.map((ev, i) => {
      const d = disp[ev.id_evento] || { total: 0, disponible: 0, vendido: 0, reservado: 0 };
      const dt = fechaEvento(ev);
      const pv = d.total ? (d.vendido / d.total) * 100 : 0, pr = d.total ? (d.reservado / d.total) * 100 : 0;
      const pocas = d.total && d.disponible / d.total < 0.15;
      return `<a class="ev-card fade-in" href="#/evento/${ev.id_evento}" style="animation-delay:${i * 40}ms">
        ${poster(ev)}
        <div class="cuerpo">
          <div class="lugar">${ICONOS.lugar}${esc(ev.escenario?.nombre || "")} · ${fmtFechaCorta(dt)} · ${fmtHora(dt)}</div>
          <div class="barra-disp" title="Vendidos ${d.vendido} · Reservados ${d.reservado} · Disponibles ${d.disponible}"><i class="v" style="width:${pv}%"></i><i class="r" style="width:${pr}%"></i></div>
          <div class="disp-txt"><span class="${pocas ? "pocas" : ""}">${d.total ? (d.disponible ? `${d.disponible} disponibles${pocas ? " · ¡últimas!" : ""}` : "Agotado") : "Sin asientos publicados"}</span><span>${Math.round(pv)}% vendido</span></div>
          <div class="pie-card"><div class="precio-desde"><small>Desde</small><b>${d.precio_desde != null ? moneda(d.precio_desde) : "—"}</b></div><span class="ver">Ver asientos ${ICONOS.flecha}</span></div>
        </div>
        <div class="fecha-badge" style="position:absolute"><b>${dt.getDate()}</b><small>${MESES[dt.getMonth()]}</small></div></a>`;
    }).join("");
    // la insignia de fecha va sobre el póster
    $$(".ev-card", g).forEach((c) => { const b = $(".fecha-badge", c); $(".poster", c).appendChild(b); });
  };
  let t;
  $("#f-q").oninput = (e) => { clearTimeout(t); t = setTimeout(() => { f.q = e.target.value.trim(); pintarGrid(); }, 160); };
  $("#f-esc").onchange = (e) => { f.escenario = e.target.value; pintarGrid(); };
  $("#f-precio").onchange = (e) => { f.precio = e.target.value; pintarGrid(); };
  $("#f-orden").onchange = (e) => { f.orden = e.target.value; pintarGrid(); };
  $("#f-disp").onchange = (e) => { f.soloDisp = e.target.checked; pintarGrid(); };
  $$("[data-mes]").forEach((b) => b.onclick = () => { f.mes = b.dataset.mes; $$("[data-mes]").forEach((x) => x.classList.toggle("on", x === b)); pintarGrid(); });
  $$("[data-gen]").forEach((b) => b.onclick = () => { f.genero = f.genero === b.dataset.gen ? "" : b.dataset.gen; $$("[data-gen]").forEach((x) => x.classList.toggle("on", x.dataset.gen === f.genero)); pintarGrid(); });
  pintarGrid();
});

// =====================================================================
// DETALLE DEL EVENTO + MAPA DE ASIENTOS EN VIVO (RF-DIS-02, RF-RES-01)
// =====================================================================
ruta("/evento/:id", async (app, { id }) => {
  const [ev, mapa, mias] = await Promise.all([
    api("eventos", `/eventos/${id}`), api("disponibilidad", `/disponibilidad/eventos/${id}`), api("reservas", "/reservas/mis")]);
  const dt = fechaEvento(ev);
  const seleccion = new Map();          // id_asiento -> {fila, numero, localidad, precio, color}
  let reserva = mias.find((r) => r.estado === "activa" && r.id_evento === ev.id_evento && r.segundos_restantes > 0) || null;
  let vence = reserva ? Date.now() + reserva.segundos_restantes * 1000 : 0;
  const infoAsiento = {};
  mapa.localidades.forEach((l, i) => l.asientos.forEach((a) => {
    infoAsiento[a.id_asiento] = { ...a, localidad: l.nombre, precio: l.precio, color: ZONA_COLORES[i % ZONA_COLORES.length] };
  }));
  const mios = () => new Set(reserva ? reserva.asientos.map((a) => a.id_asiento) : []);

  app.innerHTML = `<main>
    <a class="volver" href="#/catalogo">${ICONOS.atras} Volver al catálogo</a>
    ${ev.estado === "aplazado" ? `<div class="aviso-banda aplazado">📅<div><b>Este evento fue aplazado</b>Nueva fecha: ${fmtFechaLarga(dt)}, ${fmtHora(dt)}<br>Las boletas ya compradas siguen siendo válidas.</div></div>` : ""}
    ${ev.estado === "cancelado" ? `<div class="aviso-banda cancelado">✕<div><b>Este evento fue cancelado</b>Si compraste boletas, su valor se devolvió en créditos que puedes usar en cualquier otro evento.</div></div>` : ""}
    <section class="ev-cabecera fade-in">${poster(ev)}
      <div>${chipEstado(ev.estado)}<h1>${esc(ev.nombre)}</h1>
        <p class="desc">${esc(ev.descripcion || "")}</p>
        <div class="datos-ev">
          <div class="dato-ev"><small>Fecha</small><b>${fmtFechaLarga(dt)}</b></div>
          <div class="dato-ev"><small>Hora</small><b>${fmtHora(dt)}</b></div>
          <div class="dato-ev"><small>Escenario</small><b>${esc(ev.escenario?.nombre || "")}</b><br><span style="color:var(--tenue);font-size:.8rem">${esc(ev.escenario?.direccion || "")}</span></div>
          <div class="dato-ev"><small>Disponibles</small><b id="cnt-disp">${mapa.totales.disponible}</b> <span style="color:var(--tenue)">de ${mapa.totales.total}</span></div>
        </div></div></section>
    <div class="compra-layout">
      <section class="mapa">
        <div class="mapa-cab"><h3>Elige tus asientos</h3><span class="en-vivo">En vivo</span></div>
        <div class="leyenda" style="margin-bottom:18px">
          <span><i style="border:1.5px solid var(--borde-2);background:#fff"></i>Disponible</span>
          <span><i style="background:var(--acento)"></i>Tu selección</span>
          <span><i style="background:repeating-linear-gradient(45deg,#fbecd3 0 3px,#fff 3px 6px);border:1.5px solid #e3b46a"></i>Reservado</span>
          <span><i style="background:#e9edf2;border:1.5px solid #d5dbe4"></i>Vendido</span></div>
        <div class="escenario-tarima">ESCENARIO</div>
        <div class="scroll-mapa" id="zonas">${mapa.localidades.map((l, i) => zonaHTML(l, i)).join("") || `<div class="vacio">Este evento aún no tiene asientos publicados.</div>`}</div>
      </section>
      <aside class="panel resumen-compra" id="panel"></aside>
    </div></main>`;

  // ---- tooltip ----
  const tip = document.createElement("div"); tip.className = "tooltip"; tip.hidden = true; document.body.appendChild(tip);
  const zonas = $("#zonas");
  const ocultarTip = () => { tip.hidden = true; };
  window.addEventListener("scroll", ocultarTip, { passive: true });
  zonas.addEventListener("scroll", ocultarTip, { passive: true });
  zonas.addEventListener("pointermove", (e) => {
    const b = e.target.closest(".asiento"); if (!b) { tip.hidden = true; return; }
    const a = infoAsiento[b.dataset.id]; const r = b.getBoundingClientRect();
    const est = mios().has(a.id_asiento) ? "En tu reserva" : seleccion.has(a.id_asiento) ? "Seleccionado" : { disponible: "Disponible", reservado: "Reservado por otra persona", vendido: "Vendido" }[a.estado];
    tip.innerHTML = `${esc(a.localidad)} · Fila ${esc(a.fila)} · Asiento ${a.numero}<small>${moneda(a.precio)} · ${est}</small>`;
    tip.style.left = `${r.left + r.width / 2}px`; tip.style.top = `${r.top}px`; tip.hidden = false;
  });
  zonas.addEventListener("pointerleave", ocultarTip);
  window.addEventListener("hashchange", () => { tip.remove(); window.removeEventListener("scroll", ocultarTip); }, { once: true });

  zonas.addEventListener("click", (e) => {
    const b = e.target.closest(".asiento"); if (!b || b.disabled) return;
    if (reserva) { toast("Ya tienes una reserva activa en este evento: págala o cancélala para elegir otros asientos", "info"); return; }
    const idA = +b.dataset.id, a = infoAsiento[idA];
    if (seleccion.has(idA)) seleccion.delete(idA);
    else {
      if (seleccion.size >= 10) { toast("Puedes elegir máximo 10 asientos por reserva", "info"); return; }
      seleccion.set(idA, a);
    }
    pintarAsientos(); pintarPanel();
  });

  function pintarAsientos() {
    const m = mios();
    let libres = 0;
    $$(".asiento", zonas).forEach((b) => {
      const a = infoAsiento[b.dataset.id];
      const propio = m.has(a.id_asiento), sel = seleccion.has(a.id_asiento);
      b.className = `asiento ${b.dataset.pasillo ? "pasillo" : ""} ${propio || sel ? "sel" : a.estado !== "disponible" ? a.estado : ""}`;
      b.disabled = !propio && !sel && a.estado !== "disponible";
      if (a.estado === "disponible") libres++;
    });
    $("#cnt-disp").textContent = libres;
    mapa.localidades.forEach((l) => {
      const n = l.asientos.filter((a) => infoAsiento[a.id_asiento].estado === "disponible").length;
      const el = $(`[data-zona-disp="${l.id_localidad}"]`); if (el) el.textContent = n ? `${n} disponibles` : "Agotada";
    });
  }

  function pintarPanel() {
    const p = $("#panel"); if (!p) return;
    if (!EN_VENTA.includes(ev.estado)) { p.innerHTML = `<h3>Evento ${(ETIQUETA_ESTADO[ev.estado] || ev.estado).toLowerCase()}</h3><p style="color:var(--suave)">Este evento no admite reservas ni compras en este momento.</p>`; return; }
    if (reserva) {
      const s = Math.max(0, Math.round((vence - Date.now()) / 1000));
      p.innerHTML = `<h3>Tu reserva #${reserva.id_reserva}</h3>
        <div class="temporizador ${s < 60 ? "urgente" : ""}"><div style="flex:1"><small style="color:var(--suave)">Asientos apartados por</small><div class="barra-tiempo"><i id="bt" style="width:${(s / (reserva.segundos_inicial || 600)) * 100}%"></i></div></div><b id="reloj">${mmss(s)}</b></div>
        <div class="sel-lista">${reserva.asientos.map((a) => itemSel(a, infoAsiento[a.id_asiento]?.color, false)).join("")}</div>
        <div class="total-linea"><span>Total</span><b>${moneda(reserva.total)}</b></div>
        <button class="btn btn-primario btn-xl" id="b-pagar">Pagar ahora</button>
        <button class="btn btn-fantasma btn-xl" id="b-cancelar" style="margin-top:8px">Cancelar reserva</button>
        <div class="nota">⏳ Si no pagas antes de que termine el tiempo, la reserva expira y los asientos se liberan.</div>`;
      $("#b-pagar").onclick = () => abrirCheckout(reserva, async (resultado) => {
        if (resultado !== "abierto") { reserva = null; await refrescar(); }
      });
      $("#b-cancelar").onclick = async () => {
        if (!await confirmar("Se liberarán los asientos de tu reserva.", { si: "Cancelar reserva", peligro: true })) return;
        try { await api("reservas", `/reservas/${reserva.id_reserva}/cancelar`, { metodo: "PUT" }); toast("Reserva cancelada, los asientos quedaron libres"); reserva = null; await refrescar(); }
        catch (e) { toastError(e); }
      };
      return;
    }
    const items = [...seleccion.entries()];
    const total = items.reduce((s, [, a]) => s + Number(a.precio), 0);
    p.innerHTML = `<h3>Tu selección</h3>
      ${items.length ? `<div class="sel-lista">${items.map(([idA, a]) => itemSel({ id_asiento: idA, ...a }, a.color, true)).join("")}</div>`
        : `<div class="vacio" style="padding:26px 14px;margin-bottom:14px"><div class="grande">💺</div>Toca los asientos del mapa para elegirlos.</div>`}
      <div class="total-linea"><span>${items.length} asiento(s)</span><b>${moneda(total)}</b></div>
      <button class="btn btn-primario btn-xl" id="b-reservar" ${items.length ? "" : "disabled"}>Reservar asientos</button>
      <div class="nota">🔒 Al reservar, los asientos quedan apartados solo para ti durante 10 minutos mientras pagas.</div>
      <div class="nota">🛡 <span><b>Precio Justo:</b> si el precio de tu localidad baja después de tu compra, te devolvemos la diferencia en créditos automáticamente.</span></div>`;
    $$("[data-quitar]", p).forEach((b) => b.onclick = () => { seleccion.delete(+b.dataset.quitar); pintarAsientos(); pintarPanel(); });
    $("#b-reservar").onclick = reservar;
  }

  async function reservar() {
    const b = $("#b-reservar"); b.disabled = true; b.innerHTML = `<span class="spinner" style="width:16px;height:16px;border-width:2px"></span> Apartando…`;
    try {
      const r = await api("reservas", "/reservas", { metodo: "POST", cuerpo: { id_evento: ev.id_evento, asientos: [...seleccion.keys()] } });
      reserva = { ...r, segundos_inicial: r.segundos_restantes }; vence = Date.now() + r.segundos_restantes * 1000;
      r.asientos.forEach((a) => { infoAsiento[a.id_asiento].estado = "reservado"; });
      seleccion.clear();
      toast("¡Asientos apartados! Tienes 10 minutos para pagar");
      pintarAsientos(); pintarPanel(); revisarNotificaciones(false, true);
      abrirCheckout(reserva, async (resultado) => { if (resultado !== "abierto") { reserva = null; await refrescar(); } });
    } catch (e) {
      if (e.status === 409 && e.detalle?.asientos) {
        e.detalle.asientos.forEach((i) => { seleccion.delete(i); if (infoAsiento[i]) infoAsiento[i].estado = "reservado"; });
      }
      toastError(e); await refrescar();
    }
  }

  async function refrescar() {
    try {
      const m = await api("disponibilidad", `/disponibilidad/eventos/${id}`, { silencioso: true });
      m.localidades.forEach((l) => l.asientos.forEach((a) => { if (infoAsiento[a.id_asiento]) infoAsiento[a.id_asiento].estado = a.estado; }));
      let perdidos = 0;
      for (const idA of [...seleccion.keys()]) if (infoAsiento[idA].estado !== "disponible") { seleccion.delete(idA); perdidos++; }
      if (perdidos) toast(`${perdidos} asiento(s) de tu selección acaban de ser tomados por otra persona`, "info");
      if (reserva && Date.now() > vence) { reserva = null; toast("Tu reserva expiró y los asientos se liberaron", "info"); }
      pintarAsientos(); pintarPanel();
    } catch { /* reintenta en el siguiente ciclo */ }
  }

  pintarAsientos(); pintarPanel();
  cadaTanto(refrescar, 6000);
  cadaTanto(() => {
    if (!reserva) return;
    const s = Math.max(0, Math.round((vence - Date.now()) / 1000));
    const r = $("#reloj"); if (r) r.textContent = mmss(s);
    const bt = $("#bt"); if (bt) bt.style.width = `${(s / (reserva.segundos_inicial || 600)) * 100}%`;
    $(".temporizador")?.classList.toggle("urgente", s < 60);
    if (s === 0) refrescar();
  }, 1000);
});

function zonaHTML(l, i) {
  const color = ZONA_COLORES[i % ZONA_COLORES.length];
  const filas = {};
  l.asientos.forEach((a) => (filas[a.fila] ||= []).push(a));
  const orden = Object.keys(filas).sort((a, b) => (isNaN(a) || isNaN(b) ? a.localeCompare(b) : a - b));
  return `<div class="zona" style="--color-zona:${color}">
    <div class="zona-cab"><b style="color:${color}">${esc(l.nombre)}</b><span class="z-precio">${moneda(l.precio)}</span><span class="z-disp" data-zona-disp="${l.id_localidad}"></span></div>
    <div class="zona-filas">${orden.map((f) => {
      const lista = filas[f].sort((a, b) => a.numero - b.numero);
      const mitad = Math.ceil(lista.length / 2);
      return `<div class="fila-asientos"><span class="f-et">${esc(f)}</span>${lista.map((a, k) =>
        `<button class="asiento" data-id="${a.id_asiento}" ${k === mitad && lista.length > 9 ? 'data-pasillo="1"' : ""} aria-label="Fila ${esc(f)} asiento ${a.numero}">${a.numero}</button>`).join("")}<span class="f-et">${esc(f)}</span></div>`;
    }).join("")}</div></div>`;
}
function itemSel(a, color, quitable) {
  return `<div class="sel-item"><span class="pt" style="background:${color || "var(--acento)"}"></span>
    <div class="tx">Fila ${esc(a.fila)} · Asiento ${a.numero}<small>${esc(a.localidad)}</small></div>
    <span class="pr">${moneda(a.precio)}</span>${quitable ? `<button data-quitar="${a.id_asiento}" aria-label="Quitar">×</button>` : ""}</div>`;
}

// =====================================================================
// CHECKOUT: compra (RF-COM-01) → pago simulado (RF-PAG-01) → boletas (RF-BOL-01)
// =====================================================================
function abrirCheckout(reserva, alTerminar) {
  let resultado = "abierto";
  const vence = Date.now() + reserva.segundos_restantes * 1000;
  const m = modal("Finalizar compra", "", { alCerrar: () => alTerminar?.(resultado) });
  const ev = reserva.evento || {};
  const pasos = (n) => `<div class="pasos">${[1, 2, 3].map((i) => `<div class="${i <= n ? "on" : ""}"></div>`).join("")}</div>`;
  const reloj = () => `<div class="temporizador" style="margin-bottom:18px"><span style="flex:1;color:var(--suave);font-size:.85rem">Tiempo para completar el pago</span><b data-reloj>${mmss(Math.max(0, Math.round((vence - Date.now()) / 1000)))}</b></div>`;
  const tick = setInterval(() => {
    if (!document.body.contains(m.el)) return clearInterval(tick);
    const s = Math.max(0, Math.round((vence - Date.now()) / 1000));
    $$("[data-reloj]", m.el).forEach((r) => (r.textContent = mmss(s)));
  }, 1000);

  // Paso 1: resumen
  m.el.innerHTML = `${pasos(1)}${reloj()}
    <div style="display:flex;gap:14px;align-items:center;margin-bottom:16px"><div style="width:64px;height:64px;border-radius:10px;overflow:hidden;flex:none">${poster(ev, { titulo: false, clase: "mini-poster" })}</div>
    <div><b style="font-family:var(--display);font-size:1.1rem">${esc(ev.nombre || "")}</b><div style="color:var(--suave);font-size:.85rem">${ev.fecha ? `${fmtFechaLarga(fechaEvento(ev))} · ${fmtHora(fechaEvento(ev))}` : ""}</div></div></div>
    <div class="sel-lista">${reserva.asientos.map((a) => itemSel(a, null, false)).join("")}</div>
    <div class="total-linea"><span>Total a pagar</span><b>${moneda(reserva.total)}</b></div>
    <button class="btn btn-primario btn-xl" id="c-seguir">Continuar al pago ${ICONOS.flecha}</button>`;
  $("#c-seguir", m.el).onclick = async () => {
    const b = $("#c-seguir", m.el); b.disabled = true;
    try {
      const compra = await api("compras", "/compras", { metodo: "POST", cuerpo: { id_reserva: reserva.id_reserva } });
      pasoPago(compra);
    } catch (e) { toastError(e); b.disabled = false; if (e.status === 409) { resultado = "fallo"; m.cerrar(); } }
  };

  // Paso 2: créditos y/o tarjeta simulada
  async function pasoPago(compra) {
    m.titulo("Pago seguro (simulado)");
    let saldo = 0;
    try { saldo = (await api("pagos", "/creditos/mis")).saldo; } catch { /* sin créditos */ }
    const total = Number(compra.valor_total);
    m.el.innerHTML = `${pasos(2)}${reloj()}
      <form class="form" id="f-pago">
        ${saldo > 0 ? `<div class="caja-creditos"><label><input type="checkbox" id="usar-cred" checked> Usar mis créditos · saldo ${moneda(saldo)}</label><div class="desglose" id="desglose"></div></div>` : ""}
        <div id="zona-tarjeta" class="form">
        <div class="tarjeta-wrap"><div class="tarjeta" id="tj">
          <div class="cara"><div style="display:flex;justify-content:space-between;align-items:center"><span class="chip-t"></span><b style="letter-spacing:.1em">BOLETERÍA PAY</b></div>
            <div class="num" id="tj-num">•••• •••• •••• ••••</div>
            <div class="abajo"><div><small>Titular</small><span id="tj-tit">NOMBRE APELLIDO</span></div><div><small>Vence</small><span id="tj-ven">MM/AA</span></div></div></div>
          <div class="cara reverso"><div class="banda"></div><div class="cvv-zona" id="tj-cvv">•••</div></div></div></div>
        <label class="campo">Número de tarjeta<input name="numero_tarjeta" inputmode="numeric" autocomplete="cc-number" maxlength="23" placeholder="4242 4242 4242 4242"></label>
        <label class="campo">Titular<input name="titular" minlength="3" maxlength="80" autocomplete="cc-name" placeholder="Como aparece en la tarjeta"></label>
        <div class="fila-2"><label class="campo">Vencimiento<input name="vencimiento" placeholder="MM/AA" maxlength="5" autocomplete="cc-exp"></label>
        <label class="campo">CVV<input name="cvv" inputmode="numeric" maxlength="4" placeholder="123" autocomplete="cc-csc"></label></div>
        <div><span class="ayuda">Tarjetas de prueba (no hay cobros reales):</span><div class="pruebas">
          <button type="button" class="chip btn-chip" data-t="4242424242424242">✓ Aprobada · 4242…4242</button>
          <button type="button" class="chip btn-chip" data-t="4000000000000002">✕ Rechazada · 4000…0002</button></div></div>
        </div>
        <button class="btn btn-primario btn-xl" type="submit" id="b-pagar-final">Pagar</button>
        <div class="nota" style="justify-content:center">🔒 El número de la tarjeta no se guarda en ninguna base de datos.</div></form>`;
    const f = $("#f-pago", m.el), tj = $("#tj", m.el), chk = $("#usar-cred", m.el);
    const campos = ["numero_tarjeta", "titular", "vencimiento", "cvv"];
    const calcular = () => {
      const cred = chk?.checked ? Math.min(saldo, total) : 0;
      return { cred, resto: Math.round((total - cred) * 100) / 100 };
    };
    const actualizar = () => {
      const { cred, resto } = calcular();
      $("#zona-tarjeta", m.el).hidden = resto <= 0;
      campos.forEach((c) => { f[c].required = resto > 0; });
      $("#b-pagar-final", m.el).textContent = resto <= 0 ? `Pagar ${moneda(total)} con créditos`
        : cred > 0 ? `Pagar ${moneda(resto)} con tarjeta` : `Pagar ${moneda(total)}`;
      const d = $("#desglose", m.el);
      if (d) d.innerHTML = chk.checked ? `<div><span>Total</span><span>${moneda(total)}</span></div><div><span>Créditos</span><span class="monto-pos">− ${moneda(cred)}</span></div>
        <div><span><b>${resto > 0 ? "A pagar con tarjeta" : "A pagar"}</b></span><b>${moneda(resto)}</b></div>${saldo - cred > 0 ? `<div><span>Te quedarán</span><span>${moneda(saldo - cred)} en créditos</span></div>` : ""}` : "";
    };
    if (chk) chk.onchange = actualizar;
    actualizar();
    const sync = () => {
      const n = f.numero_tarjeta.value.replace(/\D/g, "");
      $("#tj-num", m.el).textContent = (n.padEnd(16, "•").match(/.{1,4}/g) || []).join(" ");
      $("#tj-tit", m.el).textContent = f.titular.value.toUpperCase() || "NOMBRE APELLIDO";
      $("#tj-ven", m.el).textContent = f.vencimiento.value || "MM/AA";
      $("#tj-cvv", m.el).textContent = f.cvv.value.replace(/./g, "•") || "•••";
    };
    f.numero_tarjeta.oninput = () => { const n = f.numero_tarjeta.value.replace(/\D/g, "").slice(0, 19); f.numero_tarjeta.value = n.replace(/(.{4})/g, "$1 ").trim(); sync(); };
    f.vencimiento.oninput = () => { let v = f.vencimiento.value.replace(/\D/g, "").slice(0, 4); if (v.length > 2) v = `${v.slice(0, 2)}/${v.slice(2)}`; f.vencimiento.value = v; sync(); };
    f.titular.oninput = sync; f.cvv.oninput = () => { f.cvv.value = f.cvv.value.replace(/\D/g, ""); sync(); };
    f.cvv.onfocus = () => tj.classList.add("girada"); f.cvv.onblur = () => tj.classList.remove("girada");
    $$("[data-t]", m.el).forEach((b) => b.onclick = () => {
      f.numero_tarjeta.value = b.dataset.t.replace(/(.{4})/g, "$1 ").trim();
      if (!f.titular.value) f.titular.value = `${estado.perfil?.nombre || ""} ${estado.perfil?.apellido || ""}`.trim();
      if (!f.vencimiento.value) f.vencimiento.value = "12/30";
      if (!f.cvv.value) f.cvv.value = "123";
      sync();
    });
    alEnviar(f, async (d) => {
      const { cred, resto } = calcular();
      const cuerpo = { id_compra: compra.id_compra, usar_creditos: cred > 0 };
      if (resto > 0) campos.forEach((c) => { cuerpo[c] = d[c]; });
      const pago = await api("pagos", "/pagos", { metodo: "POST", cuerpo });
      pasoResultado(pago, compra);
    });
  }

  // Paso 3: resultado
  function pasoResultado(pago, compra) {
    clearInterval(tick);
    revisarNotificaciones(false, true);
    if (pago.saldo_creditos !== undefined) { estado.saldo = pago.saldo_creditos; pintarCreditos(); }
    if (pago.estado === "aprobado") {
      resultado = "pagado";
      m.titulo("¡Compra confirmada!");
      confeti();
      m.el.innerHTML = `${pasos(3)}<div class="resultado"><div class="icono-res ok">✓</div>
        <h3 style="font-size:1.4rem;margin-bottom:6px">¡Pago aprobado!</h3>
        <p style="color:var(--suave);margin:0 0 18px">Referencia <span class="mono">${esc(pago.referencia)}</span> · ${moneda(pago.valor)}
          ${pago.valor_creditos > 0 ? `<br>${moneda(pago.valor_creditos)} pagados con créditos${pago.metodo === "mixto" ? ` y ${moneda(pago.valor - pago.valor_creditos)} con tarjeta` : ""}` : ""}</p>
        <div class="sel-lista" style="text-align:left">${pago.boletas.map((b) => `<div class="sel-item"><img src="/api/boletas/boletas/qr/${esc(b.codigo_boleta)}.svg" alt="QR" style="width:42px;height:42px;background:#fff;border-radius:6px;padding:2px">
          <div class="tx">${esc(b.localidad || "")} · Fila ${esc(b.fila)} · Asiento ${b.numero}<small class="mono">${esc(b.codigo_boleta)}</small></div><span class="pr">${moneda(b.precio)}</span></div>`).join("")}</div>
        ${pago.mensaje && pago.mensaje !== "Pago aprobado" ? `<p style="color:var(--aviso)">${esc(pago.mensaje)}</p>` : ""}
        <a class="btn btn-primario btn-xl" href="#/boletas" id="r-ver">Ver mis boletas</a></div>`;
      $("#r-ver", m.el).onclick = () => m.cerrar();
    } else {
      resultado = "rechazado";
      m.titulo("Pago rechazado");
      m.el.innerHTML = `${pasos(3)}<div class="resultado"><div class="icono-res mal">✕</div>
        <h3 style="font-size:1.3rem;margin-bottom:6px">El banco rechazó el pago</h3>
        <p style="color:var(--suave);margin:0 0 20px">${esc(pago.mensaje)} No se generaron boletas. Puedes intentarlo de nuevo eligiendo tus asientos otra vez.</p>
        <button class="btn btn-sec btn-xl" id="r-cerrar">Volver al mapa de asientos</button></div>`;
      $("#r-cerrar", m.el).onclick = () => m.cerrar();
    }
  }
}

// =====================================================================
// MIS RESERVAS (RF-RES-02, RF-RES-03)
// =====================================================================
ruta("/reservas", async (app) => {
  const lista = await api("reservas", "/reservas/mis");
  const t0 = Date.now();
  const activas = lista.filter((r) => r.estado === "activa" && r.segundos_restantes > 0);
  const otras = lista.filter((r) => !activas.includes(r));
  const item = (r) => {
    const ev = r.evento || { id_evento: r.id_evento, nombre: `Evento ${r.id_evento}` };
    return `<div class="item-res fade-in">${poster(ev)}<div>
      <h3>${esc(ev.nombre)} <span class="estado e-${r.estado}">${r.estado}</span>${ev.estado && ev.estado !== "programado" ? chipEstado(ev.estado) : ""}</h3>
      <div class="meta"><span>Reserva #${r.id_reserva}</span>${ev.fecha ? `<span>${fmtFechaCorta(fechaEvento(ev))} · ${fmtHora(fechaEvento(ev))}</span>` : ""}<span>${esc(ev.escenario?.nombre || "")}</span><span>${moneda(r.total)}</span></div>
      <div class="asientos-chips">${r.asientos.map((a) => `<span class="chip">${esc(a.localidad)} · ${esc(a.fila)}${a.numero}</span>`).join("")}</div></div>
      <div class="acc">${r.estado === "activa" && r.segundos_restantes > 0 ? `<span>⏳ <span class="reloj" data-vence="${t0 + r.segundos_restantes * 1000}">${mmss(r.segundos_restantes)}</span></span>
        <button class="btn btn-primario btn-s" data-pagar="${r.id_reserva}">Pagar</button><button class="btn btn-fantasma btn-s" data-cancelar="${r.id_reserva}">Cancelar</button>`
        : r.estado === "completada" ? `<a class="btn btn-sec btn-s" href="#/boletas">Ver boletas</a>` : `<a class="btn btn-fantasma btn-s" href="#/evento/${r.id_evento}">Ver evento</a>`}</div></div>`;
  };
  app.innerHTML = `<main><div class="titulo-seccion"><div><h1>Mis reservas</h1><p>Los asientos reservados se apartan por 10 minutos mientras completas el pago.</p></div><a class="btn btn-sec" href="#/catalogo">Explorar eventos</a></div>
    ${activas.length ? `<h3 style="margin:0 0 12px">Activas</h3><div class="lista" style="margin-bottom:30px">${activas.map(item).join("")}</div>` : ""}
    ${otras.length ? `<h3 style="margin:0 0 12px;color:var(--suave)">Anteriores</h3><div class="lista">${otras.map(item).join("")}</div>` : ""}
    ${!lista.length ? `<div class="vacio"><div class="grande">🎫</div><h3>Aún no tienes reservas</h3><p>Elige un evento del catálogo y aparta tus asientos.</p><a class="btn btn-primario" href="#/catalogo">Ver catálogo</a></div>` : ""}</main>`;
  $$("[data-pagar]", app).forEach((b) => b.onclick = () => {
    const r = lista.find((x) => x.id_reserva === +b.dataset.pagar);
    const restante = Math.round((+$(`[data-vence]`, b.parentElement).dataset.vence - Date.now()) / 1000);
    abrirCheckout({ ...r, segundos_restantes: restante }, (res) => { if (res !== "abierto") render(); });
  });
  $$("[data-cancelar]", app).forEach((b) => b.onclick = async () => {
    if (!await confirmar("Se liberarán los asientos de esta reserva.", { si: "Cancelar reserva", peligro: true })) return;
    try { await api("reservas", `/reservas/${b.dataset.cancelar}/cancelar`, { metodo: "PUT" }); toast("Reserva cancelada"); render(); } catch (e) { toastError(e); }
  });
  cadaTanto(() => {
    $$("[data-vence]", app).forEach((el) => {
      const s = Math.max(0, Math.round((+el.dataset.vence - Date.now()) / 1000));
      el.textContent = mmss(s);
      if (s === 0 && !el.dataset.fin) { el.dataset.fin = 1; setTimeout(render, 2500); }
    });
  }, 1000);
});

// =====================================================================
// MIS BOLETAS (RF-BOL-02)
// =====================================================================
ruta("/boletas", async (app) => {
  const lista = await api("boletas", "/boletas/mis");
  let filtro = "vigente";
  const pintar = () => {
    const vis = lista.filter((b) => filtro === "todas" || b.estado === filtro)
      .sort((a, b) => (a.evento && b.evento ? fechaEvento(a.evento) - fechaEvento(b.evento) : 0));
    $("#bol", app).innerHTML = vis.length ? vis.map((b, i) => {
      const ev = b.evento || { nombre: `Evento ${b.id_evento}`, id_evento: b.id_evento };
      const col = ZONA_COLORES[hash(b.localidad || "") % ZONA_COLORES.length];
      return `<article class="boleta ${b.estado} fade-in" style="--b-color:${col};animation-delay:${i * 40}ms" data-codigo="${esc(b.codigo_boleta)}">
        <div class="b-izq"><div style="display:flex;justify-content:space-between;gap:8px"><span class="chip">${genero(ev).n}</span><span class="estado e-${b.estado}">${b.estado}</span></div>
          <h3>${esc(ev.nombre)}</h3>
          <div style="color:var(--suave);font-size:.84rem">${ev.fecha ? `${fmtFechaLarga(fechaEvento(ev))} · ${fmtHora(fechaEvento(ev))}` : ""}<br>${esc(ev.escenario?.nombre || "")}</div>
          <div class="b-datos"><div><small>Localidad</small><b>${esc(b.localidad || "")}</b></div><div><small>Fila</small><b>${esc(b.fila || "")}</b></div><div><small>Asiento</small><b>${b.numero ?? ""}</b></div></div>
          <div style="display:flex;justify-content:space-between;align-items:center"><b style="color:var(--oro)">${moneda(b.precio)}</b><span class="ayuda">${b.estado === "cancelada" ? "Reembolsada en créditos" : `Compra #${b.id_compra}`}</span></div></div>
        <div class="b-der"><img class="qr" src="/api/boletas/boletas/qr/${esc(b.codigo_boleta)}.svg" alt="QR ${esc(b.codigo_boleta)}" loading="lazy"><span class="codigo">${esc(b.codigo_boleta)}</span></div>
        ${b.estado !== "vigente" ? `<span class="sello" style="color:${b.estado === "usada" ? "var(--acento)" : "var(--error)"}">${b.estado.toUpperCase()}</span>` : ""}</article>`;
    }).join("") : `<div class="vacio" style="grid-column:1/-1"><div class="grande">🎟</div><h3>${lista.length ? "No hay boletas con este filtro" : "Todavía no tienes boletas"}</h3><p>Cuando pagues una reserva, tus boletas aparecerán aquí con su código QR.</p><a class="btn btn-primario" href="#/catalogo">Ver eventos</a></div>`;
    $$(".boleta", app).forEach((el) => el.onclick = () => verBoleta(lista.find((b) => b.codigo_boleta === el.dataset.codigo)));
  };
  const n = (e) => lista.filter((b) => b.estado === e).length;
  app.innerHTML = `<main><div class="titulo-seccion"><div><h1>Mis boletas</h1><p>Presenta el código QR en la entrada del evento. Una boleta por asiento.</p></div>
    <button class="btn btn-sec no-imprimir" onclick="window.print()">🖨 Imprimir</button></div>
    <div class="chips-mes no-imprimir"><button class="chip btn-chip on" data-f="vigente">Vigentes (${n("vigente")})</button><button class="chip btn-chip" data-f="usada">Usadas (${n("usada")})</button><button class="chip btn-chip" data-f="cancelada">Canceladas (${n("cancelada")})</button><button class="chip btn-chip" data-f="todas">Todas (${lista.length})</button></div>
    <div class="grid-boletas" id="bol"></div></main>`;
  $$("[data-f]", app).forEach((b) => b.onclick = () => { filtro = b.dataset.f; $$("[data-f]", app).forEach((x) => x.classList.toggle("on", x === b)); pintar(); });
  pintar();
});
function verBoleta(b) {
  const ev = b.evento || {};
  modal(esc(ev.nombre || "Boleta"), `<div style="text-align:center">
    <img src="/api/boletas/boletas/qr/${esc(b.codigo_boleta)}.svg" alt="QR" style="width:220px;height:220px;background:#fff;border-radius:16px;padding:12px">
    <div class="mono" style="font-size:1.1rem;margin:12px 0 4px;letter-spacing:.1em">${esc(b.codigo_boleta)}</div><span class="estado e-${b.estado}">${b.estado}</span>
    <div class="datos-ev" style="text-align:left;margin-top:20px">
      <div class="dato-ev"><small>Fecha</small><b>${ev.fecha ? fmtFechaLarga(fechaEvento(ev)) : ""}</b></div>
      <div class="dato-ev"><small>Hora</small><b>${ev.fecha ? fmtHora(fechaEvento(ev)) : ""}</b></div>
      <div class="dato-ev"><small>Escenario</small><b>${esc(ev.escenario?.nombre || "")}</b></div>
      <div class="dato-ev"><small>Ubicación</small><b>${esc(b.localidad)} · Fila ${esc(b.fila)} · ${b.numero}</b></div>
      <div class="dato-ev"><small>Precio</small><b>${moneda(b.precio)}</b></div>
      <div class="dato-ev"><small>Titular</small><b>${esc(estado.perfil?.nombre || "")} ${esc(estado.perfil?.apellido || "")}</b></div></div></div>`);
}

// =====================================================================
// HISTORIAL (RF-COM-03, RNF06)
// =====================================================================
ruta("/historial", async (app) => {
  const h = await api("compras", "/historial");
  const filas = h.reservas.map((r) => {
    const ev = r.evento || { nombre: `Evento ${r.id_evento}` };
    return `<tr><td><b>${esc(ev.nombre)}</b><div style="color:var(--tenue);font-size:.78rem">${ev.fecha ? `${fmtFechaCorta(fechaEvento(ev))} · ${esc(ev.escenario?.nombre || "")}` : ""} ${ev.estado && ev.estado !== "programado" ? chipEstado(ev.estado) : ""}</div></td>
      <td class="mono">#${r.id_reserva}</td><td>${fmtFechaHora(r.fecha_reserva)}</td><td>${r.asientos.length}</td>
      <td><span class="estado e-${r.estado}">${r.estado}</span></td>
      <td>${r.compra ? `<span class="estado e-${r.compra.estado}">${r.compra.estado}</span> <span class="mono">#${r.compra.id_compra}</span>` : "—"}</td>
      <td style="text-align:right;font-weight:600">${moneda(r.compra?.valor_total ?? r.total)}</td></tr>`;
  }).join("");
  app.innerHTML = `<main><div class="titulo-seccion"><div><h1>Historial</h1><p>Todas tus reservas y compras, incluso de eventos que ya se realizaron.</p></div></div>
    <div class="stats"><div class="stat"><span class="ic">🎫</span><small>Reservas</small><b>${h.resumen.reservas}</b></div>
      <div class="stat"><span class="ic">✅</span><small>Compras pagadas</small><b>${h.resumen.compras_pagadas}</b></div>
      <div class="stat"><span class="ic">💳</span><small>Total pagado</small><b style="color:var(--oro)">${moneda(h.resumen.total_pagado)}</b></div></div>
    ${filas ? `<div class="tabla-wrap"><table class="tabla"><thead><tr><th>Evento</th><th>Reserva</th><th>Fecha</th><th>Asientos</th><th>Estado reserva</th><th>Compra</th><th style="text-align:right">Valor</th></tr></thead><tbody>${filas}</tbody></table></div>`
      : `<div class="vacio"><div class="grande">🗂</div><h3>Tu historial está vacío</h3></div>`}</main>`;
});

// =====================================================================
// MIS CRÉDITOS (evento cancelado y Precio Justo Garantizado)
// =====================================================================
ruta("/creditos", async (app) => {
  const c = await api("pagos", "/creditos/mis");
  estado.saldo = c.saldo; pintarCreditos();
  const CONCEPTO = { evento_cancelado: "Evento cancelado", precio_justo: "Precio Justo", pago_compra: "Pago de compra" };
  app.innerHTML = `<main><div class="titulo-seccion"><div><h1>Mis créditos</h1><p>Saldo a tu favor para pagar cualquier evento, total o parcialmente.</p></div><a class="btn btn-sec" href="#/catalogo">Usar en un evento</a></div>
    <div class="perfil-grid" style="margin-bottom:22px">
      <section class="panel"><small style="color:var(--tenue);text-transform:uppercase;letter-spacing:.08em;font-size:.72rem;font-weight:600">Saldo disponible</small>
        <div class="saldo-grande">${moneda(c.saldo)}</div><p style="color:var(--suave);margin:6px 0 0">Al pagar una compra, marca «Usar mis créditos». Si no alcanzan, pagas el resto con tarjeta.</p></section>
      <section class="panel"><h3 style="margin-bottom:10px">¿De dónde salen?</h3>
        <p style="margin:0 0 8px;color:var(--suave)"><b style="color:var(--texto)">Evento cancelado:</b> te devolvemos el valor de tus boletas.</p>
        <p style="margin:0;color:var(--suave)"><b style="color:var(--texto)">🛡 Precio Justo Garantizado:</b> si el precio de tu localidad baja después de comprar, te devolvemos la diferencia automáticamente. Nunca pagas más que quien compró después.</p></section></div>
    ${c.movimientos.length ? `<div class="tabla-wrap"><table class="tabla"><thead><tr><th>Fecha</th><th>Concepto</th><th>Detalle</th><th style="text-align:right">Monto</th></tr></thead><tbody>
      ${c.movimientos.map((m) => `<tr><td>${fmtFechaHora(m.fecha)}</td><td><span class="chip">${CONCEPTO[m.concepto] || m.concepto}</span></td><td style="color:var(--suave)">${esc(m.descripcion)}</td>
        <td style="text-align:right" class="${m.tipo === "abono" ? "monto-pos" : "monto-neg"}">${m.tipo === "abono" ? "+" : "−"} ${moneda(m.monto)}</td></tr>`).join("")}</tbody></table></div>`
      : `<div class="vacio"><div class="grande">💳</div><h3>Aún no tienes créditos</h3><p>Aparecerán aquí si un evento se cancela o si baja el precio de una localidad que compraste.</p></div>`}</main>`;
});

// =====================================================================
// PERFIL (RF-USR-02, RF-USR-03)
// =====================================================================
ruta("/perfil", async (app) => {
  const [p, s] = await Promise.all([api("usuarios", "/usuarios/me"), api("acceso", "/auth/me")]);
  estado.perfil = p; estado.sesion = s; guardar("perfil", p); guardar("sesion", s);
  app.innerHTML = `<main><div class="titulo-seccion"><div><h1>Mi perfil</h1><p>Solo tú puedes ver y modificar tus datos.</p></div></div>
    <div class="perfil-grid">
      <section class="panel"><div style="display:flex;gap:14px;align-items:center;margin-bottom:20px"><span class="avatar" style="width:56px;height:56px;font-size:1.2rem">${iniciales(p.nombre, p.apellido)}</span>
        <div><h2>${esc(p.nombre)} ${esc(p.apellido)}</h2><span class="estado ${s.rol === "administrador" ? "e-pendiente" : "e-completada"}">${esc(s.rol)}</span></div></div>
        <div class="datos-perfil"><div><small>Correo</small><b>${esc(p.correo)}</b></div><div><small>Teléfono</small><b>${esc(p.telefono)}</b></div>
          <div><small>Documento</small><b>${esc(p.documento)}</b></div><div><small>ID de usuario</small><b>#${p.id_usuario}</b></div></div>
        <p style="color:var(--tenue);font-size:.8rem;margin:20px 0 6px">Permisos de tu rol</p><div class="permisos">${s.permisos.map((x) => `<span class="chip">${esc(x.replaceAll("_", " "))}</span>`).join("")}</div></section>
      <section class="panel"><h3 style="margin-bottom:6px">Actualizar datos de contacto</h3><p style="color:var(--suave);font-size:.88rem;margin:0 0 18px">El documento de identidad no se puede modificar.</p>
        <form class="form" id="f-perfil"><label class="campo">Correo<input name="correo" type="email" value="${esc(p.correo)}" required></label>
          <label class="campo">Teléfono<input name="telefono" value="${esc(p.telefono)}" required pattern="\\+?[0-9 ]{7,20}"></label>
          <label class="campo">Documento<input value="${esc(p.documento)}" readonly></label>
          <button class="btn btn-primario" type="submit">Guardar cambios</button></form></section></div></main>`;
  alEnviar($("#f-perfil", app), async (d) => {
    const n = await api("usuarios", "/usuarios/me", { metodo: "PUT", cuerpo: d });
    estado.perfil = n; guardar("perfil", n); toast("Datos actualizados"); render();
  });
});

// =====================================================================
// ESTADO DEL SISTEMA (13 microservicios)
// =====================================================================
ruta("/sistema", async (app) => {
  const pintar = async () => {
    const e = await fetch("/api/estado").then((r) => r.json());
    const sv = $("#sv", app); if (!sv) return;
    $("#modo", app).innerHTML = `<span class="chip">Modo: ${esc(e.modo)}</span> <span class="chip">Base de datos: ${esc(e.base_de_datos)}</span> <span class="estado ${e.todos_ok ? "e-ok" : "e-caido"}">${e.todos_ok ? "Todo operativo" : "Hay servicios caídos"}</span>`;
    sv.innerHTML = e.servicios.map((s) => `<a class="servicio" href="/api/${s.servicio}/docs" target="_blank" rel="noopener"><span class="luz ${s.ok ? "ok" : "mal"}"></span>
      <div><b>${s.servicio}</b><small>${s.ok ? "En línea" : "Sin respuesta"} · esquema_${s.servicio}</small></div></a>`).join("");
  };
  app.innerHTML = `<main><div class="titulo-seccion"><div><h1>Estado del sistema</h1><p>Cada microservicio tiene su propio esquema de base de datos. Toca uno para abrir su documentación (Swagger).</p></div><div id="modo"></div></div>
    <div class="servicios" id="sv"><div class="cargando"><div class="spinner"></div></div></div>
    <section class="panel" style="margin-top:24px"><h3 style="margin-bottom:10px">Flujo de una compra</h3>
      <p style="color:var(--suave);margin:0;line-height:1.8">Catálogo (<b>Eventos</b> + <b>Escenarios</b> + <b>Disponibilidad</b>) → <b>Reservas</b> aparta los asientos de forma atómica en <b>Disponibilidad</b> → <b>Compras</b> calcula el total con <b>Localidades</b> y <b>Asientos</b> → <b>Pagos</b> aprueba o rechaza → <b>Boletas</b> emite una por asiento → <b>Notificaciones</b> avisa al usuario → <b>Auditoría</b> registra cada paso. <b>Control de Acceso</b> valida la sesión y los permisos en cada petición.</p></section></main>`;
  await pintar();
  cadaTanto(pintar, 8000);
}, { publica: true });

window.addEventListener("DOMContentLoaded", () => { render(); if (estado.token) revisarNotificaciones(); });
