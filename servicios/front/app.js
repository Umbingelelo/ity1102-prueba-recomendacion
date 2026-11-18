// Front genérico: el formulario y la forma del resultado los describe el dominio en GET /api/caso.
// Así el mismo front sirve para los tres casos. Todas las llamadas van al gateway (rutas relativas).
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(ruta, opciones = {}) {
  const clave = sessionStorage.getItem("clave");
  const headers = { "Content-Type": "application/json", ...(clave ? { "X-API-Key": clave } : {}) };
  const r = await fetch(ruta, { ...opciones, headers });
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) {
    const detalle = Array.isArray(cuerpo.detail)
      ? cuerpo.detail.map((d) => `${d.loc.slice(1).join(".")}: ${d.msg}`).join(" · ")
      : cuerpo.detail || r.statusText;
    throw new Error(`${r.status} · ${detalle}`);
  }
  return cuerpo;
}

function mostrarError(e) {
  $("error").hidden = !e;
  $("error").textContent = e ? `Error: ${e.message}` : "";
}

function prepararClave(requiere) {
  if (!requiere) return;
  $("bloque-clave").hidden = false;
  $("clave").value = sessionStorage.getItem("clave") || "";
  $("clave").addEventListener("change", (ev) => sessionStorage.setItem("clave", ev.target.value.trim()));
}

function tabla(filas) {
  if (!filas || !filas.length) return '<p class="suave">Sin datos todavía.</p>';
  const cols = Object.keys(filas[0]);
  const celda = (v) => {
    if (Array.isArray(v) && v.every((x) => x && typeof x === "object" && "descripcion" in x))
      return esc(v.map((x) => x.descripcion).join(" · "));
    if (typeof v === "object" && v !== null) return `<code>${esc(JSON.stringify(v).slice(0, 160))}</code>`;
    const t = String(v ?? "");
    return t.length > 180 ? `<span title="${esc(t)}">${esc(t.slice(0, 180))}…</span>` : esc(t);
  };
  return `<table><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${filas
    .map((f) => `<tr>${cols.map((c) => `<td>${celda(f[c])}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;
}

const etiqueta = (t) => `<span class="etiqueta ${esc(t)}">${esc(t)}</span>`;

// ---------------------------------------------------------------- página de predicción
function campo(c) {
  const id = `c_${c.nombre}`;
  if (c.tipo === "opciones")
    return `<label>${esc(c.etiqueta)}<select id="${id}" name="${c.nombre}">${c.opciones
      .map((o) => `<option ${o === c.valor ? "selected" : ""}>${esc(o)}</option>`)
      .join("")}</select></label>`;
  if (c.tipo === "area")
    return `<label class="ancho">${esc(c.etiqueta)}<textarea id="${id}" name="${c.nombre}">${esc(c.valor)}</textarea></label>`;
  const tipo = c.tipo === "numero" ? "number" : "text";
  return `<label>${esc(c.etiqueta)}<input id="${id}" name="${c.nombre}" type="${tipo}" step="any" value="${esc(c.valor)}"></label>`;
}

function leerFormulario(campos) {
  const datos = {};
  for (const c of campos) {
    const v = $(`c_${c.nombre}`).value.trim();
    if (v === "") continue;   // vacío = no se manda: el dominio usa su valor por defecto
    datos[c.nombre] = c.tipo === "numero" ? Number(v) : v;
  }
  return datos;
}

function detalle(r) {
  const partes = [];
  if (r.mensaje) partes.push(`<p>${esc(r.mensaje)}</p>`);
  if (r.razones) partes.push(`<h3>Por qué</h3>${tabla(r.razones)}`);
  if (r.alternativas) partes.push(`<h3>Otras opciones del modelo</h3>${tabla(r.alternativas)}`);
  if (r.productos) partes.push(`<h3>Productos</h3>${tabla(r.productos)}`);
  if (r.articulos) partes.push(`<h3>Artículos de ayuda</h3>${tabla(r.articulos)}`);
  if (r.categorias) partes.push(`<h3>Categorías según el modelo</h3>${tabla(r.categorias)}`);
  return partes.join("");
}

async function esperarLLM(id) {
  $("llm").innerHTML = `<p>${etiqueta("pendiente")} El texto del LLM llega por la cola…</p>`;
  for (let i = 0; i < 40; i++) {
    await new Promise((ok) => setTimeout(ok, 1500));
    const p = await api(`/api/predicciones/${id}`);
    if (p.estado_llm === "listo") {
      $("llm").innerHTML = `<h3>Texto del LLM ${etiqueta("listo")} <small class="suave">${p.latencia_llm_ms} ms</small></h3><div class="llm">${esc(p.texto_llm)}</div>`;
      return;
    }
    if (p.estado_llm === "degradado") {
      $("llm").innerHTML = `<p>${etiqueta("degradado")} Sin texto del LLM (${esc(p.motivo_llm)}). La predicción sigue siendo válida.</p>`;
      return;
    }
  }
  $("llm").innerHTML = `<p>${etiqueta("pendiente")} El LLM no ha respondido todavía. Revisa el worker.</p>`;
}

async function historial() {
  try {
    const filas = await api("/api/predicciones?limite=10");
    $("historial").querySelector("tbody").innerHTML = filas
      .map((f) => `<tr><td>${esc(new Date(f.creada).toLocaleString("es-CL"))}</td><td>${etiqueta(f.decision)}</td>
        <td>${f.probabilidad ?? "—"}</td><td>${esc(f.origen)}</td><td><code>${esc(f.version_modelo)}</code></td>
        <td>${f.latencia_ms}</td><td>${etiqueta(f.estado_llm)}</td></tr>`)
      .join("");
  } catch (e) { /* sin clave todavía: se intentará después */ }
}

async function listas(definiciones) {
  $("listas").innerHTML = "";
  for (const l of definiciones || []) {
    try {
      const filas = await api(l.ruta);
      $("listas").insertAdjacentHTML("beforeend", `<section><h2>${esc(l.titulo)} <small class="suave">GET ${esc(l.ruta)}</small></h2>${tabla(filas.slice(0, 10))}</section>`);
    } catch (e) { /* sin clave todavía */ }
  }
}

async function paginaPrediccion() {
  const caso = await api("/api/caso");
  document.title = caso.titulo;
  $("titulo").textContent = caso.titulo;
  $("descripcion").textContent = caso.descripcion;
  prepararClave(caso.requiere_clave);
  $("formulario").innerHTML = caso.campos.map(campo).join("") + `<button type="submit">${esc(caso.boton)}</button>`;
  $("formulario").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const boton = ev.target.querySelector("button");
    boton.disabled = true;
    mostrarError(null);
    try {
      const r = await api("/api/predict", { method: "POST", body: JSON.stringify(leerFormulario(caso.campos)) });
      $("resultado").hidden = false;
      const prob = r.probabilidad == null ? "—" : `${(r.probabilidad * 100).toFixed(1)}%`;
      $("resumen").innerHTML = `<p>${etiqueta(r.decision)} &nbsp; probabilidad <b>${prob}</b> · origen ${etiqueta(r.origen)}
        · modelo <code>${esc(r.version_modelo)}</code> · ${r.latencia_ms} ms</p>`;
      $("detalle").innerHTML = detalle(r);
      $("llm").innerHTML = "";
      historial();
      listas(caso.listas);
      if (r.estado_llm === "pendiente") await esperarLLM(r.id);
      else if (r.estado_llm === "degradado") $("llm").innerHTML = `<p>${etiqueta("degradado")} La cola no está disponible: la predicción se entregó sin texto del LLM.</p>`;
      listas(caso.listas);
    } catch (e) {
      mostrarError(e);
    } finally {
      boton.disabled = false;
    }
  });
  historial();
  listas(caso.listas);
}

// ---------------------------------------------------------------- dashboard
const tarjeta = (t, v) => `<div class="tarjeta"><span class="suave">${esc(t)}</span><b>${esc(v ?? "—")}</b></div>`;

async function paginaDashboard() {
  const caso = await api("/api/caso");
  $("titulo").textContent = `Dashboard · ${caso.titulo}`;
  prepararClave(caso.requiere_clave);
  const actualizar = async () => {
    try {
      const s = await api("/api/health");
      const p = s.piezas;
      $("salud").innerHTML = [
        tarjeta("Sistema", s.estado), tarjeta("Base", p.base), tarjeta("Modelo", `${p.ia.motor ?? ""} ${p.ia.modelo ?? p.ia.estado}`),
        tarjeta("Versión", p.ia.version_modelo), tarjeta("Cola", p.cola.estado), tarjeta("LLM", p.llm),
        tarjeta("Autenticación", s.autenticacion),
      ].join("");
      const d = await api("/api/dashboard");
      const g = d.general;
      $("general").innerHTML = [
        tarjeta("Predicciones", g.total), tarjeta("Por el modelo", g.por_modelo), tarjeta("Por reserva", g.por_reserva),
        tarjeta("Por regla", g.por_regla), tarjeta("Latencia p50 (ms)", g.latencia_p50_ms), tarjeta("Latencia p95 (ms)", g.latencia_p95_ms),
        tarjeta("LLM listo", g.llm_listo), tarjeta("LLM degradado", g.llm_degradado),
      ].join("");
      $("propio").innerHTML = Object.entries(d)
        .filter(([k]) => !["caso", "general"].includes(k))
        .map(([k, v]) => (Array.isArray(v) ? `<h3>${esc(k.replaceAll("_", " "))}</h3>${tabla(v)}` : `<div class="tarjetas">${tarjeta(k.replaceAll("_", " "), typeof v === "object" ? JSON.stringify(v) : v)}</div>`))
        .join("");
      mostrarError(null);
    } catch (e) {
      mostrarError(e);
    }
  };
  await actualizar();
  setInterval(actualizar, 10000);
}

(location.pathname.endsWith("dashboard.html") ? paginaDashboard() : paginaPrediccion()).catch(mostrarError);
