/* =====================================================================
   Boletería · administración (RN20: solo rol administrador)
   ===================================================================== */
"use strict";

const TABS_ADMIN = [["resumen", "📊 Resumen"], ["eventos", "🎤 Eventos"], ["escenarios", "🏟 Escenarios y asientos"],
  ["usuarios", "👥 Usuarios y roles"], ["auditoria", "🧾 Auditoría"], ["boletas", "🎟 Validar boleta"], ["indicadores", "📈 Indicadores"]];

function marcoAdmin(app, tab, titulo, sub) {
  app.innerHTML = `<main><div class="titulo-seccion"><div><h1>${titulo}</h1><p>${sub}</p></div><div id="acc-tab"></div></div>
    <nav class="admin-tabs">${TABS_ADMIN.map(([k, t]) => `<a href="#/admin/${k}" class="${k === tab ? "on" : ""}">${t}</a>`).join("")}</nav>
    <div id="admin-cuerpo"><div class="cargando"><div class="spinner"></div></div></div></main>`;
  return $("#admin-cuerpo", app);
}
ruta("/admin", (app) => navegar("/admin/resumen"), { admin: true });
ruta("/admin/:tab", async (app, { tab }) => {
  const vistas = { resumen: adminResumen, eventos: adminEventos, escenarios: adminEscenarios, usuarios: adminUsuarios, auditoria: adminAuditoria, boletas: adminBoletas, indicadores: adminIndicadores };
  await (vistas[tab] || adminResumen)(app);
}, { admin: true });

// ---------------------------------------------------------------- resumen
async function adminResumen(app) {
  const c = marcoAdmin(app, "resumen", "Panel de administración", "Ventas, ocupación y actividad del sistema.");
  const [ventas, evs, activas, cred] = await Promise.all([api("boletas", "/boletas/resumen"), api("eventos", "/eventos/todos"),
    api("reservas", "/reservas?estado=activa"), api("pagos", "/creditos/resumen")]);
  const prog = evs.filter((e) => EN_VENTA.includes(e.estado));
  const sumar = (f) => cred.filter(f).reduce((a, x) => a + x.total, 0);
  const disp = prog.length ? await api("disponibilidad", `/disponibilidad/resumen?eventos_ids=${prog.map((e) => e.id_evento).join(",")}`) : [];
  const tot = disp.reduce((a, d) => ({ t: a.t + d.total, v: a.v + d.vendido }), { t: 0, v: 0 });
  const maxIng = Math.max(1, ...ventas.eventos.map((e) => e.ingresos));
  const dmap = Object.fromEntries(disp.map((d) => [d.id_evento, d]));
  c.innerHTML = `<div class="stats">
      <div class="stat"><span class="ic">💰</span><small>Ingresos</small><b style="color:var(--oro)">${moneda(ventas.total_ingresos)}</b></div>
      <div class="stat"><span class="ic">🎟</span><small>Boletas vendidas</small><b>${ventas.total_boletas}</b></div>
      <div class="stat"><span class="ic">🎤</span><small>Eventos a la venta</small><b>${prog.length}</b></div>
      <div class="stat"><span class="ic">📈</span><small>Ocupación promedio</small><b>${tot.t ? Math.round((tot.v / tot.t) * 100) : 0}%</b></div>
      <div class="stat"><span class="ic">⏳</span><small>Reservas activas</small><b>${activas.length}</b></div>
      <div class="stat"><span class="ic">💳</span><small>Créditos devueltos</small><b>${moneda(sumar((x) => x.tipo === "abono"))}</b>
        <div class="ayuda">${moneda(sumar((x) => x.concepto === "precio_justo"))} por Precio Justo · ${moneda(sumar((x) => x.tipo === "uso"))} ya usados</div></div></div>
    <section class="panel"><h3 style="margin-bottom:18px">Ingresos por evento</h3><div class="barras">
      ${ventas.eventos.length ? ventas.eventos.map((e) => `<div class="barra-fila"><span><b>${esc(e.evento || `Evento ${e.id_evento}`)}</b><br><span style="color:var(--tenue);font-size:.78rem">${e.vendidas} boletas${dmap[e.id_evento] ? ` · ${Math.round(dmap[e.id_evento].vendido / Math.max(1, dmap[e.id_evento].total) * 100)}% ocupado` : ""}</span></span>
        <div class="bar"><i style="width:0" data-w="${(e.ingresos / maxIng) * 100}"></i></div><span class="val">${moneda(e.ingresos)}</span></div>`).join("") : `<div class="vacio">Aún no hay ventas</div>`}</div></section>`;
  requestAnimationFrame(() => setTimeout(() => $$("[data-w]", c).forEach((i) => (i.style.width = `${i.dataset.w}%`)), 50));
}

// ---------------------------------------------------------------- eventos
async function adminEventos(app) {
  const c = marcoAdmin(app, "eventos", "Eventos", "Registra, edita (cambiar la fecha lo deja aplazado), cancela con reembolso en créditos, reactiva o marca como realizados.");
  const [evs, escs] = await Promise.all([api("eventos", "/eventos/todos"), api("escenarios", "/escenarios")]);
  $("#acc-tab", app).innerHTML = `<button class="btn btn-primario" id="nuevo-ev">+ Nuevo evento</button>`;
  const disp = evs.length ? Object.fromEntries((await api("disponibilidad", `/disponibilidad/resumen?eventos_ids=${evs.map((e) => e.id_evento).join(",")}`)).map((d) => [d.id_evento, d])) : {};
  const acciones = (e) => {
    if (EN_VENTA.includes(e.estado)) return `<button class="btn btn-sec btn-s" data-ed="${e.id_evento}">Editar</button>
        <button class="btn btn-sec btn-s" data-pub="${e.id_evento}" title="Publicar asientos nuevos del escenario">Publicar</button>
        <button class="btn btn-ok btn-s" data-real="${e.id_evento}">Realizado</button><button class="btn btn-peligro btn-s" data-can="${e.id_evento}">Cancelar</button>`;
    if (e.estado === "cancelado") return `<button class="btn btn-primario btn-s" data-ed="${e.id_evento}">Editar y reactivar</button>`;
    return `<a class="btn btn-fantasma btn-s" href="#/evento/${e.id_evento}">Ver</a>`;
  };
  c.innerHTML = evs.length ? `<div class="tabla-wrap"><table class="tabla"><thead><tr><th></th><th>Evento</th><th>Fecha</th><th>Escenario</th><th>Asientos</th><th>Estado</th><th></th></tr></thead><tbody>
    ${evs.map((e) => { const d = disp[e.id_evento] || {}; return `<tr><td style="width:52px"><div style="width:44px;height:44px;border-radius:8px;overflow:hidden">${poster(e, { titulo: false, clase: "mini-poster" })}</div></td>
      <td><b>${esc(e.nombre)}</b><div class="mono" style="color:var(--tenue)">#${e.id_evento}${e.imagen ? " · con imagen" : ""}</div></td>
      <td>${fmtFechaCorta(fechaEvento(e))}<br><span style="color:var(--tenue)">${fmtHora(fechaEvento(e))}</span></td><td>${esc(e.escenario?.nombre || "")}</td>
      <td><span style="color:var(--ok)">${d.disponible ?? 0}</span> / <span style="color:var(--aviso)">${d.reservado ?? 0}</span> / <span style="color:var(--acento)">${d.vendido ?? 0}</span><div class="ayuda">disp. / res. / vend.</div></td>
      <td>${chipEstado(e.estado)}</td>
      <td><div class="acc">${acciones(e)}</div></td></tr>`; }).join("")}
    </tbody></table></div><p class="ayuda" style="margin-top:10px">Cambiar la fecha u hora deja el evento <b>Aplazado</b> y avisa a quienes ya compraron. Al <b>cancelarlo</b>, las boletas vendidas se reembolsan en créditos y los asientos se liberan; luego puedes editarlo para <b>reactivarlo</b>. Los registros se conservan (RN14).</p>`
    : `<div class="vacio"><div class="grande">🎤</div><h3>Aún no hay eventos</h3></div>`;

  const formEvento = (e) => {
    if (!escs.length && !e) { toast("Primero registra un escenario", "info"); return; }
    const reactivar = e?.estado === "cancelado";
    let nuevaImagen = null, quitarImagen = false;
    const m = modal(reactivar ? "Reactivar evento" : e ? "Editar evento" : "Nuevo evento", `<form class="form" id="f-ev">
      ${reactivar ? `<div class="aviso-banda justo" style="margin:0">↺<div><b>El evento está cancelado</b>Al guardar vuelve a la venta: queda <b>Programado</b> si mantienes la fecha o <b>Aplazado</b> si la cambias. Los asientos están libres; quienes compraron tienen sus créditos para volver a comprar.</div></div>` : ""}
      <label class="campo">Nombre<input name="nombre" required maxlength="120" value="${esc(e?.nombre || "")}" placeholder="Ej. Concierto de rock en vivo"></label>
      <label class="campo">Descripción<textarea name="descripcion" maxlength="2000" placeholder="Artistas, género, edad mínima…">${esc(e?.descripcion || "")}</textarea></label>
      ${e ? `<label class="campo">Escenario<input value="${esc(e.escenario?.nombre || "")}" readonly></label>` : `<label class="campo">Escenario<select name="id_escenario" required>${escs.map((s) => `<option value="${s.id_escenario}">${esc(s.nombre)} (cap. ${s.capacidad})</option>`).join("")}</select></label>`}
      <div class="fila-2"><label class="campo">Fecha<input type="date" name="fecha" required value="${e?.fecha || ""}"></label>
      <label class="campo">Hora<input type="time" name="hora" required value="${(e?.hora || "20:00").slice(0, 5)}"></label></div>
      ${e && !reactivar ? `<span class="ayuda" style="margin-top:-6px">Si cambias la fecha o la hora, el evento quedará <b>Aplazado</b> y se avisará a quienes ya compraron.</span>` : ""}
      <div class="campo" style="display:grid;gap:6px;font-size:.82rem;color:var(--suave);font-weight:600">Imagen del evento
        <div class="subir-imagen"><div class="vista" id="vista-img">${e?.imagen ? `<img src="${esc(e.imagen)}" alt="">` : "Sin imagen<br>(póster generado)"}</div>
          <div style="display:grid;gap:8px"><input type="file" id="archivo-img" accept="image/jpeg,image/png,image/webp">
            <span class="ayuda">JPG, PNG o WEBP. Se ajusta automáticamente antes de subirla.</span>
            ${e?.imagen ? `<button type="button" class="btn btn-fantasma btn-s" id="quitar-img" style="justify-self:start">Quitar imagen</button>` : ""}</div></div></div>
      <button class="btn btn-primario" type="submit">${reactivar ? "Reactivar evento" : e ? "Guardar cambios" : "Crear evento y publicar disponibilidad"}</button></form>`, { ancho: true });
    $("#archivo-img", m.el).onchange = async (ev) => {
      const f = ev.target.files[0]; if (!f) return;
      try { nuevaImagen = await imagenADataURL(f); quitarImagen = false; $("#vista-img", m.el).innerHTML = `<img src="${nuevaImagen}" alt="">`; }
      catch (er) { ev.target.value = ""; toastError(er); }
    };
    $("#quitar-img", m.el)?.addEventListener("click", () => { quitarImagen = true; nuevaImagen = null; $("#vista-img", m.el).innerHTML = "Sin imagen<br>(póster generado)"; });
    alEnviar($("#f-ev", m.el), async (d) => {
      let id = e?.id_evento;
      if (e) {
        const r = await api("eventos", `/eventos/${e.id_evento}`, { metodo: "PUT", cuerpo: { nombre: d.nombre, descripcion: d.descripcion || null, fecha: d.fecha, hora: d.hora } });
        if (r.cambio === "reactivado") toast(`Evento reactivado · quedó ${ETIQUETA_ESTADO[r.estado].toLowerCase()} y de nuevo a la venta`);
        else if (r.cambio === "aplazado") toast(`Evento aplazado · ${r.notificados} comprador(es) notificado(s)`);
        else toast("Evento actualizado");
      } else {
        const r = await api("eventos", "/eventos", { metodo: "POST", cuerpo: { ...d, id_escenario: +d.id_escenario, descripcion: d.descripcion || null } });
        id = r.id_evento;
        toast(`Evento creado · ${r.disponibilidad.publicados} asientos publicados`);
        if (!r.disponibilidad.publicados) toast("El escenario no tiene asientos todavía: créalos en «Escenarios y asientos» y luego usa «Publicar»", "info", 8000);
      }
      if (nuevaImagen) { await api("eventos", `/eventos/${id}/imagen`, { metodo: "PUT", cuerpo: { imagen: nuevaImagen } }); toast("Imagen guardada"); }
      else if (quitarImagen) await api("eventos", `/eventos/${id}/imagen`, { metodo: "DELETE" });
      m.cerrar(); render();
    });
  };
  $("#nuevo-ev", app).onclick = () => formEvento(null);
  $$("[data-ed]", c).forEach((b) => b.onclick = () => formEvento(evs.find((e) => e.id_evento === +b.dataset.ed)));
  $$("[data-pub]", c).forEach((b) => b.onclick = async () => {
    try { const r = await api("eventos", `/eventos/${b.dataset.pub}/publicar`, { metodo: "POST" }); toast(`${r.publicados} asiento(s) nuevos publicados · ${r.total} en total`); render(); } catch (e) { toastError(e); }
  });
  const cambiar = (idE, est, txt) => async () => {
    if (!await confirmar(txt, { si: est === "cancelado" ? "Cancelar evento" : "Marcar realizado", peligro: est === "cancelado" })) return;
    try {
      const r = await api("eventos", `/eventos/${idE}/estado`, { metodo: "PUT", cuerpo: { estado: est } });
      toast(est === "cancelado"
        ? `Evento cancelado · ${r.boletas_canceladas ?? 0} boletas reembolsadas: ${moneda(r.creditos_devueltos || 0)} en créditos a ${r.usuarios_reembolsados ?? 0} comprador(es)`
        : "Evento marcado como realizado", "ok", 7000);
      render();
    } catch (e) { toastError(e); }
  };
  $$("[data-can]", c).forEach((b) => b.onclick = cambiar(+b.dataset.can, "cancelado", "El evento dejará de admitir reservas y compras. Las reservas activas se cancelan, las boletas vendidas se <b>reembolsan en créditos</b> y los asientos quedan libres. Podrás reactivarlo después editándolo."));
  $$("[data-real]", c).forEach((b) => b.onclick = cambiar(+b.dataset.real, "realizado", "El evento saldrá del catálogo. Su historial de reservas, compras y boletas se conserva."));
}

// ---------------------------------------------------------------- escenarios, localidades y asientos
async function adminEscenarios(app, seleccionado) {
  const c = marcoAdmin(app, "escenarios", "Escenarios, localidades y asientos", "RF-ESC, RF-LOC y RF-ASI: la base física sobre la que se publican los eventos.");
  const escs = await api("escenarios", "/escenarios");
  $("#acc-tab", app).innerHTML = `<button class="btn btn-primario" id="nuevo-esc">+ Nuevo escenario</button>`;
  let actual = seleccionado || escs[0]?.id_escenario;
  c.innerHTML = `<div class="dos-col"><div class="lista" id="l-esc"></div><div id="d-esc"></div></div>`;

  const pintarLista = () => {
    $("#l-esc", c).innerHTML = escs.length ? escs.map((e) => `<div class="esc-item ${e.id_escenario === actual ? "on" : ""}" data-id="${e.id_escenario}">
      <b>${esc(e.nombre)}</b><small>${esc(e.direccion)}</small><small>Capacidad: ${e.capacidad}</small></div>`).join("") : `<div class="vacio">Sin escenarios</div>`;
    $$(".esc-item", c).forEach((el) => el.onclick = () => { actual = +el.dataset.id; pintarLista(); pintarDetalle(); });
  };
  const formEsc = (e) => {
    const m = modal(e ? "Editar escenario" : "Nuevo escenario", `<form class="form" id="f-esc">
      <label class="campo">Nombre<input name="nombre" required maxlength="100" value="${esc(e?.nombre || "")}"></label>
      <label class="campo">Dirección<input name="direccion" required maxlength="150" value="${esc(e?.direccion || "")}"></label>
      <label class="campo">Capacidad total<input type="number" name="capacidad" required min="1" value="${e?.capacidad || ""}"></label>
      <button class="btn btn-primario" type="submit">${e ? "Guardar" : "Crear escenario"}</button></form>`);
    alEnviar($("#f-esc", m.el), async (d) => {
      const r = await api("escenarios", e ? `/escenarios/${e.id_escenario}` : "/escenarios", { metodo: e ? "PUT" : "POST", cuerpo: { ...d, capacidad: +d.capacidad } });
      toast(e ? "Escenario actualizado" : "Escenario creado"); m.cerrar(); adminEscenarios(app, r.id_escenario);
    });
  };
  async function pintarDetalle() {
    const d = $("#d-esc", c);
    const e = escs.find((x) => x.id_escenario === actual);
    if (!e) { d.innerHTML = `<div class="vacio"><div class="grande">🏟</div><h3>Registra tu primer escenario</h3></div>`; return; }
    d.innerHTML = `<div class="cargando"><div class="spinner"></div></div>`;
    const locs = await api("localidades", `/localidades?id_escenario=${e.id_escenario}`);
    const conteos = await Promise.all(locs.map((l) => api("asientos", `/asientos?id_localidad=${l.id_localidad}`).then((a) => a.length)));
    const usada = locs.reduce((s, l) => s + l.capacidad, 0);
    d.innerHTML = `<section class="panel"><div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px">
        <div><h2>${esc(e.nombre)}</h2><p style="color:var(--suave);margin:4px 0 0">${esc(e.direccion)} · ${usada} de ${e.capacidad} lugares asignados a localidades</p></div>
        <div style="display:flex;gap:8px"><button class="btn btn-sec btn-s" id="ed-esc">Editar</button><button class="btn btn-peligro btn-s" id="del-esc">Eliminar</button></div></div>
      <div class="barra-disp" style="margin-bottom:20px"><i class="v" style="width:${Math.min(100, (usada / e.capacidad) * 100)}%;background:var(--acento-2)"></i></div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><h3>Localidades</h3><button class="btn btn-primario btn-s" id="nueva-loc">+ Localidad</button></div>
      ${locs.length ? `<div class="tabla-wrap"><table class="tabla"><thead><tr><th>Localidad</th><th>Precio</th><th>Capacidad</th><th>Asientos creados</th><th></th></tr></thead><tbody>
        ${locs.map((l, i) => `<tr><td><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${ZONA_COLORES[i % ZONA_COLORES.length]};margin-right:8px"></span><b>${esc(l.nombre)}</b></td>
          <td style="color:var(--oro)">${moneda(l.precio)}</td><td>${l.capacidad}</td>
          <td>${conteos[i]} <span class="ayuda">/ ${l.capacidad}</span>${conteos[i] < l.capacidad ? ` <span class="estado e-pendiente">faltan ${l.capacidad - conteos[i]}</span>` : ` <span class="estado e-ok">completa</span>`}</td>
          <td><div class="acc"><button class="btn btn-sec btn-s" data-gen="${l.id_localidad}" ${conteos[i] >= l.capacidad ? "disabled" : ""}>Generar asientos</button>
            <button class="btn btn-sec btn-s" data-edl="${l.id_localidad}">Editar</button>${conteos[i] ? "" : `<button class="btn btn-peligro btn-s" data-dell="${l.id_localidad}">Eliminar</button>`}</div></td></tr>`).join("")}
      </tbody></table></div>` : `<div class="vacio">Este escenario aún no tiene localidades. Crea zonas como VIP, Platea o General.</div>`}
      <p class="ayuda" style="margin-top:12px">Los asientos nuevos se publican automáticamente en los eventos a la venta de este escenario.</p></section>`;
    $("#ed-esc", d).onclick = () => formEsc(e);
    $("#del-esc", d).onclick = async () => {
      if (!await confirmar(`Se eliminará «${esc(e.nombre)}». Solo es posible si no tiene eventos ni localidades (RF-ESC-03).`, { si: "Eliminar", peligro: true })) return;
      try { await api("escenarios", `/escenarios/${e.id_escenario}`, { metodo: "DELETE" }); toast("Escenario eliminado"); adminEscenarios(app); } catch (er) { toastError(er); }
    };
    const formLoc = (l) => {
      const m = modal(l ? "Editar localidad" : `Nueva localidad · ${esc(e.nombre)}`, `<form class="form" id="f-loc">
        <label class="campo">Nombre<input name="nombre" required maxlength="60" value="${esc(l?.nombre || "")}" placeholder="VIP, Platea, General…"></label>
        <div class="fila-2"><label class="campo">Precio (COP)<input type="number" name="precio" required min="0" step="any" value="${l?.precio ?? ""}"></label>
        <label class="campo">Capacidad (asientos)<input type="number" name="capacidad" required min="1" value="${l?.capacidad || ""}"></label></div>
        ${l ? `<span class="ayuda">🛡 <b>Precio Justo:</b> si bajas el precio, quienes ya compraron en esta localidad reciben la diferencia en créditos. Subirlo no afecta las boletas emitidas (RF-LOC-02).</span>` : `<span class="ayuda">Quedan ${e.capacidad - usada} lugares del escenario sin asignar.</span>`}
        <button class="btn btn-primario" type="submit">${l ? "Guardar" : "Crear localidad"}</button></form>`);
      alEnviar($("#f-loc", m.el), async (x) => {
        const cuerpo = { nombre: x.nombre, precio: +x.precio, capacidad: +x.capacidad };
        if (l) {
          const r = await api("localidades", `/localidades/${l.id_localidad}`, { metodo: "PUT", cuerpo });
          toast("Localidad actualizada");
          if (r.precio_justo?.total) toast(`🛡 Precio Justo: se devolvieron ${moneda(r.precio_justo.total)} en créditos a ${r.precio_justo.usuarios} comprador(es)`, "ok", 8000);
        } else {
          await api("localidades", "/localidades", { metodo: "POST", cuerpo: { ...cuerpo, id_escenario: e.id_escenario } });
          toast("Localidad creada");
        }
        m.cerrar(); pintarDetalle();
      });
    };
    $("#nueva-loc", d).onclick = () => formLoc(null);
    $$("[data-edl]", d).forEach((b) => b.onclick = () => formLoc(locs.find((l) => l.id_localidad === +b.dataset.edl)));
    $$("[data-dell]", d).forEach((b) => b.onclick = async () => {
      if (!await confirmar("Se eliminará la localidad.", { si: "Eliminar", peligro: true })) return;
      try { await api("localidades", `/localidades/${b.dataset.dell}`, { metodo: "DELETE" }); toast("Localidad eliminada"); pintarDetalle(); } catch (er) { toastError(er); }
    });
    $$("[data-gen]", d).forEach((b) => b.onclick = () => {
      const i = locs.findIndex((l) => l.id_localidad === +b.dataset.gen), l = locs[i];
      const libre = l.capacidad - conteos[i];
      const porFila = Math.min(20, libre), filas = Math.max(1, Math.floor(libre / porFila));
      const m = modal(`Generar asientos · ${esc(l.nombre)}`, `<form class="form" id="f-gen">
        <p style="color:var(--suave);margin:0">Crea una cuadrícula de filas (A, B, C…) con asientos numerados. Quedan <b>${libre}</b> lugares disponibles en la localidad.</p>
        <div class="fila-3"><label class="campo">Filas<input type="number" name="filas" min="1" max="26" value="${filas}" required></label>
          <label class="campo">Asientos por fila<input type="number" name="asientos_por_fila" min="1" max="60" value="${porFila}" required></label>
          <label class="campo">Fila inicial<input name="fila_inicial" value="${conteos[i] ? "" : "A"}" maxlength="2" required placeholder="A"></label></div>
        <div id="vista-gen" class="ayuda"></div>
        <button class="btn btn-primario" type="submit">Generar</button></form>`);
      const f = $("#f-gen", m.el);
      const prev = () => { const n = (+f.filas.value || 0) * (+f.asientos_por_fila.value || 0); $("#vista-gen", m.el).innerHTML = `Se crearán hasta <b>${n}</b> asientos ${n > libre ? `<span style="color:var(--error)">(supera los ${libre} disponibles)</span>` : ""}`; };
      f.oninput = prev; prev();
      alEnviar(f, async (x) => {
        const r = await api("asientos", "/asientos/generar", { metodo: "POST", cuerpo: { id_localidad: l.id_localidad, filas: +x.filas, asientos_por_fila: +x.asientos_por_fila, fila_inicial: x.fila_inicial.toUpperCase() } });
        toast(`${r.creados} asientos creados · ${r.publicados_en_eventos} publicados en eventos`); m.cerrar(); pintarDetalle();
      });
    });
  }
  $("#nuevo-esc", app).onclick = () => formEsc(null);
  pintarLista(); pintarDetalle();
}

// ---------------------------------------------------------------- usuarios y roles
async function adminUsuarios(app) {
  const c = marcoAdmin(app, "usuarios", "Usuarios y roles", "Asigna roles a los usuarios registrados (CU-04, RF-ACC-02).");
  const [usuarios, roles] = await Promise.all([api("usuarios", "/usuarios?limit=500"), api("acceso", "/roles")]);
  c.innerHTML = `<div class="stats">${roles.map((r) => `<div class="stat"><small>Rol</small><b style="font-size:1.25rem">${esc(r.nombre)}</b>
      <div style="color:var(--suave);font-size:.82rem;margin:6px 0 10px">${esc(r.descripcion || "")} · ${usuarios.filter((u) => u.rol === r.nombre).length} usuario(s)</div>
      <div class="permisos">${r.permisos.map((p) => `<span class="chip" style="font-size:.66rem">${esc(p.replaceAll("_", " "))}</span>`).join("")}</div></div>`).join("")}</div>
    <div style="margin-bottom:12px"><input id="b-usr" placeholder="Buscar por nombre, correo o documento…" style="max-width:380px"></div>
    <div class="tabla-wrap"><table class="tabla"><thead><tr><th>Usuario</th><th>Correo</th><th>Teléfono</th><th>Documento</th><th>Rol</th></tr></thead><tbody id="t-usr"></tbody></table></div>`;
  const pintar = (q = "") => {
    q = q.toLowerCase();
    $("#t-usr", c).innerHTML = usuarios.filter((u) => !q || `${u.nombre} ${u.apellido} ${u.correo} ${u.documento}`.toLowerCase().includes(q)).map((u) => `<tr>
      <td><div style="display:flex;gap:10px;align-items:center"><span class="avatar">${iniciales(u.nombre, u.apellido)}</span><div><b>${esc(u.nombre)} ${esc(u.apellido)}</b><div class="mono" style="color:var(--tenue)">#${u.id_usuario}</div></div></div></td>
      <td>${esc(u.correo)}</td><td>${esc(u.telefono)}</td><td class="mono">${esc(u.documento)}</td>
      <td><select data-rol="${u.id_usuario}" ${u.id_usuario === estado.sesion.id_usuario ? 'title="Tu propio rol"' : ""}>${roles.map((r) => `<option ${r.nombre === u.rol ? "selected" : ""}>${esc(r.nombre)}</option>`).join("")}</select></td></tr>`).join("");
    $$("[data-rol]", c).forEach((s) => s.onchange = async () => {
      const u = usuarios.find((x) => x.id_usuario === +s.dataset.rol), anterior = u.rol;
      try { await api("acceso", `/credenciales/${u.id_usuario}/rol`, { metodo: "PUT", cuerpo: { rol: s.value } }); u.rol = s.value; toast(`${u.nombre} ahora es ${s.value}`); }
      catch (e) { s.value = anterior; toastError(e); }
    });
  };
  $("#b-usr", c).oninput = (e) => pintar(e.target.value);
  pintar();
}

// ---------------------------------------------------------------- auditoría
async function adminAuditoria(app) {
  const c = marcoAdmin(app, "auditoria", "Auditoría", "Registro inmutable de las operaciones críticas (RF-AUD-01 a 03, RN19). No se puede editar ni borrar.");
  const [acciones, usuarios] = await Promise.all([api("auditoria", "/auditoria/acciones"), api("usuarios", "/usuarios?limit=500")]);
  const f = { accion: "", id_usuario: "", desde: "", hasta: "", offset: 0 };
  const LIM = 25;
  c.innerHTML = `<div class="filtros" style="grid-template-columns:repeat(4,1fr)">
      <select id="a-acc"><option value="">Todas las acciones</option>${acciones.map((a) => `<option>${esc(a)}</option>`).join("")}</select>
      <select id="a-usr"><option value="">Todos los usuarios</option>${usuarios.map((u) => `<option value="${u.id_usuario}">${esc(u.nombre)} ${esc(u.apellido)}</option>`).join("")}</select>
      <input type="date" id="a-desde" title="Desde"><input type="date" id="a-hasta" title="Hasta"></div>
    <div class="tabla-wrap"><table class="tabla"><thead><tr><th>#</th><th>Fecha y hora</th><th>Usuario</th><th>Acción</th><th>Entidad</th><th>Detalle</th></tr></thead><tbody id="t-aud"></tbody></table></div>
    <div class="paginacion"><span id="a-info"></span><button class="btn btn-sec btn-s" id="a-prev">← Anterior</button><button class="btn btn-sec btn-s" id="a-sig">Siguiente →</button></div>`;
  const cargar = async () => {
    const qs = new URLSearchParams({ limit: LIM, offset: f.offset });
    ["accion", "id_usuario", "desde", "hasta"].forEach((k) => f[k] && qs.set(k, f[k]));
    const r = await api("auditoria", `/auditoria?${qs}`);
    $("#t-aud", c).innerHTML = r.items.map((a) => `<tr><td class="mono">${a.id_auditoria}</td><td>${fmtFechaHora(a.fecha_hora)}</td>
      <td>${a.usuario ? esc(a.usuario) : `<span style="color:var(--tenue)">${a.id_usuario ? `#${a.id_usuario}` : "sistema"}</span>`}</td>
      <td><span class="chip mono">${esc(a.accion)}</span></td><td>${esc(a.entidad)}${a.id_entidad ? ` <span class="mono" style="color:var(--tenue)">#${a.id_entidad}</span>` : ""}</td>
      <td style="color:var(--suave);max-width:320px">${esc(a.detalle || "")}</td></tr>`).join("") || `<tr><td colspan="6"><div class="vacio" style="border:0">Sin registros con estos filtros</div></td></tr>`;
    $("#a-info", c).textContent = r.total ? `${f.offset + 1}–${Math.min(f.offset + LIM, r.total)} de ${r.total}` : "0 registros";
    $("#a-prev", c).disabled = f.offset === 0; $("#a-sig", c).disabled = f.offset + LIM >= r.total;
  };
  const cambio = (k) => (e) => { f[k] = e.target.value; f.offset = 0; cargar().catch(toastError); };
  $("#a-acc", c).onchange = cambio("accion"); $("#a-usr", c).onchange = cambio("id_usuario");
  $("#a-desde", c).onchange = cambio("desde"); $("#a-hasta", c).onchange = cambio("hasta");
  $("#a-prev", c).onclick = () => { f.offset = Math.max(0, f.offset - LIM); cargar(); };
  $("#a-sig", c).onclick = () => { f.offset += LIM; cargar(); };
  await cargar();
}

// ---------------------------------------------------------------- validar boleta
async function adminBoletas(app) {
  const c = marcoAdmin(app, "boletas", "Validar boleta", "Consulta una boleta por su código y regístrala como usada al ingresar al evento.");
  c.innerHTML = `<div class="dos-col"><section class="panel"><form class="form" id="f-bol"><label class="campo">Código de la boleta<input name="codigo" required placeholder="BOL-XXXXXXXXXX" style="font-family:monospace;text-transform:uppercase;letter-spacing:.08em"></label>
    <button class="btn btn-primario" type="submit">Consultar</button></form></section><div id="r-bol"><div class="vacio"><div class="grande">🔎</div>Escribe o escanea el código impreso bajo el QR.</div></div></div>`;
  const mostrar = (b) => {
    const ev = b.evento || {};
    $("#r-bol", c).innerHTML = `<section class="panel fade-in"><div style="display:flex;gap:20px;flex-wrap:wrap;align-items:center">
      <img src="/api/boletas/boletas/qr/${esc(b.codigo_boleta)}.svg" style="width:130px;height:130px;background:#fff;border-radius:12px;padding:8px" alt="QR">
      <div style="flex:1;min-width:220px"><span class="estado e-${b.estado}">${b.estado}</span><h2 style="margin:8px 0 4px">${esc(ev.nombre || "")}</h2>
        <div style="color:var(--suave)">${ev.fecha ? `${fmtFechaLarga(fechaEvento(ev))} · ${fmtHora(fechaEvento(ev))}` : ""} · ${esc(ev.escenario?.nombre || "")}</div>
        <div class="datos-ev"><div class="dato-ev"><small>Titular</small><b>${esc(b.titular || "—")}</b></div><div class="dato-ev"><small>Ubicación</small><b>${esc(b.localidad)} · ${esc(b.fila)}${b.numero}</b></div><div class="dato-ev"><small>Precio</small><b>${moneda(b.precio)}</b></div></div></div></div>
      ${b.estado === "vigente" ? `<button class="btn btn-ok btn-xl" style="margin-top:18px" id="usar">✓ Registrar ingreso (marcar como usada)</button>` : `<p style="color:var(--aviso);margin:16px 0 0">Esta boleta no es válida para ingresar: está ${b.estado}.</p>`}</section>`;
    $("#usar", c)?.addEventListener("click", async () => {
      try { mostrar({ ...b, ...(await api("boletas", `/boletas/${b.codigo_boleta}/usar`, { metodo: "PUT" })), titular: b.titular }); toast("Ingreso registrado"); } catch (e) { toastError(e); }
    });
  };
  alEnviar($("#f-bol", c), async (d) => mostrar(await api("boletas", `/boletas/${encodeURIComponent(d.codigo.trim().toUpperCase())}`)));
}

// ---------------------------------------------------------------- indicadores (Data Warehouse · Sprints 7 y 8)
async function adminIndicadores(app) {
  const c = marcoAdmin(app, "indicadores", "Indicadores", "Dashboard calculado sobre el Data Warehouse (esquema en estrella), que el ETL actualiza a partir de los 13 microservicios.");
  $("#acc-tab", app).innerHTML = `<button class="btn btn-primario" id="btn-etl">⟳ Ejecutar ETL</button>`;
  $("#btn-etl", app).onclick = async (e) => {
    e.target.disabled = true;
    try {
      const r = await api("analitica", "/analitica/etl", { metodo: "POST" });
      if (r.estado === "ok") toast(`ETL listo en ${r.segundos} s · ${r.filas.fact_venta} boletas cargadas${r.calidad.cuadra ? " · cuadra con el origen" : ""}`, "ok");
      else toast(r.detalle || r.error || "El ETL no terminó", "error");
      await pintar();
    } catch (err) { toastError(err); } finally { e.target.disabled = false; }
  };
  const pct = (v) => `${Number(v || 0).toLocaleString("es-CO", { maximumFractionDigits: 1 })}%`;
  const barras = (filas, valor, etiqueta, detalle, fmt = moneda) => {
    const max = Math.max(1, ...filas.map(valor));
    return filas.length ? `<div class="barras">${filas.map((f) => `<div class="barra-fila"><span><b>${esc(etiqueta(f))}</b><br><span style="color:var(--tenue);font-size:.78rem">${detalle(f)}</span></span>
      <div class="bar"><i style="width:0" data-w="${(valor(f) / max) * 100}"></i></div><span class="val">${fmt(valor(f))}</span></div>`).join("")}</div>` : `<div class="vacio">Sin datos. Ejecuta el ETL.</div>`;
  };
  async function pintar() {
    const [d, ejec] = await Promise.all([api("analitica", "/analitica/indicadores"), api("analitica", "/analitica/etl/ejecuciones")]);
    const k = d.kpi;
    const ult = ejec[0];
    c.innerHTML = `<p class="ayuda" style="margin-bottom:14px">${d.actualizado ? `Datos actualizados: ${fmtFechaHora(d.actualizado)}` : "El Data Warehouse aún no se ha cargado."} · El ETL corre solo cada pocos minutos y también puedes ejecutarlo con el botón.</p>
    <div class="stats">
      <div class="stat"><span class="ic">💰</span><small>Ingresos</small><b style="color:var(--oro)">${moneda(k.ingresos)}</b><div class="ayuda">${k.compras} compras · ticket promedio ${moneda(k.ticket_promedio)}</div></div>
      <div class="stat"><span class="ic">🎟</span><small>Boletas vendidas</small><b>${k.boletas_vendidas}</b><div class="ayuda">${k.boletas_usadas} usadas · ${k.boletas_canceladas} anuladas</div></div>
      <div class="stat"><span class="ic">📈</span><small>Ocupación (a la venta)</small><b>${pct(k.ocupacion)}</b></div>
      <div class="stat"><span class="ic">🔁</span><small>Conversión reserva → compra</small><b>${pct(k.conversion)}</b><div class="ayuda">${k.reservas} reservas · ${pct(k.expiracion)} expiradas</div></div>
      <div class="stat"><span class="ic">💳</span><small>Créditos abonados</small><b>${moneda(k.creditos_abonados)}</b><div class="ayuda">${moneda(k.creditos_usados)} usados · saldo ${moneda(k.creditos_saldo)}</div></div>
      <div class="stat"><span class="ic">⚖️</span><small>Precio Justo devuelto</small><b>${moneda(k.precio_justo)}</b></div>
    </div>
    <section class="panel"><h3 style="margin-bottom:18px">Ingresos y ocupación por evento</h3>
      ${barras(d.por_evento, (e) => e.ingresos, (e) => e.evento, (e) => `${e.escenario} · ${e.estado} · ${e.boletas} boletas · ${pct(e.ocupacion)} ocupado`)}</section>
    <div class="grid-2" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px">
      <section class="panel"><h3 style="margin-bottom:18px">Ingresos por localidad</h3>
        ${barras(d.por_localidad, (l) => l.ingresos, (l) => l.localidad, (l) => `${l.escenario} · ${l.boletas} boletas`)}</section>
      <section class="panel"><h3 style="margin-bottom:18px">Medio de pago</h3>
        ${barras(d.por_metodo, (m) => m.ingresos, (m) => ({ tarjeta: "Tarjeta", creditos: "Créditos", mixto: "Mixto" }[m.metodo] || m.metodo), (m) => `${m.compras} compras`)}
        <h3 style="margin:22px 0 18px">Ventas por día</h3>
        ${barras(d.por_dia, (x) => x.ingresos, (x) => fmtFechaCorta(new Date(`${x.fecha}T00:00`)), (x) => `${x.boletas} boletas`)}</section>
    </div>
    <section class="panel"><h3 style="margin-bottom:12px">Bitácora del ETL</h3>
      ${ejec.length ? `<div class="tabla-wrap"><table class="tabla"><thead><tr><th>#</th><th>Inicio</th><th>Origen</th><th>Estado</th><th>Boletas</th><th>Calidad</th></tr></thead><tbody>
      ${ejec.slice(0, 8).map((e) => `<tr><td>${e.id_ejecucion}</td><td>${fmtFechaHora(e.inicio)}</td><td>${e.origen}</td><td>${e.estado}</td><td>${e.detalle?.filas?.fact_venta ?? "—"}</td><td>${e.detalle?.calidad ? (e.detalle.calidad.cuadra ? "✔ cuadra con el origen" : "✖ no cuadra") : esc(e.detalle?.error || "—")}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="vacio">Aún no hay ejecuciones.</div>`}</section>`;
    requestAnimationFrame(() => setTimeout(() => $$("[data-w]", c).forEach((i) => (i.style.width = `${i.dataset.w}%`)), 50));
  }
  await pintar();
}
