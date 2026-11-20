/* SplitFácil · app.js
   Mejoras de la interfaz que sirven en todas las páginas. Todo es "progresivo":
   si el JavaScript no carga, la app sigue funcionando con formularios normales. */
(function () {
  "use strict";

  const $ = (selector, contexto = document) => contexto.querySelector(selector);
  const $$ = (selector, contexto = document) => Array.from(contexto.querySelectorAll(selector));
  const token = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  /* ---------- Avisos (mensajes flash) ---------- */
  function cerrarAviso(aviso) {
    aviso.classList.add("aviso-sale");
    setTimeout(() => aviso.remove(), 280);
  }
  $$(".aviso").forEach((aviso) => {
    const boton = $(".aviso-cerrar", aviso);
    if (boton) boton.addEventListener("click", () => cerrarAviso(aviso));
    // Los éxitos y datos informativos se van solos; los errores esperan a que la persona los cierre.
    const espera = aviso.classList.contains("aviso-error") ? 14000 : 7000;
    setTimeout(() => { if (aviso.isConnected) cerrarAviso(aviso); }, espera);
  });

  /* ---------- Menús desplegables: se cierran al hacer clic fuera o con Escape ---------- */
  document.addEventListener("click", (evento) => {
    $$("details.menu[open]").forEach((menu) => { if (!menu.contains(evento.target)) menu.open = false; });
  });
  document.addEventListener("keydown", (evento) => {
    if (evento.key !== "Escape") return;
    $$("details.menu[open]").forEach((menu) => {
      menu.open = false;
      const resumen = $("summary", menu);
      if (resumen) resumen.focus();
    });
  });

  /* ---------- Confirmar acciones peligrosas (<form data-confirmar="..."> ) ---------- */
  const dialogo = $("#dialogo-confirmar");
  document.addEventListener("submit", (evento) => {
    const formulario = evento.target;
    const mensaje = formulario.dataset ? formulario.dataset.confirmar : null;
    if (!mensaje || formulario.dataset.confirmado === "1") return;
    evento.preventDefault();
    const enviar = () => {
      formulario.dataset.confirmado = "1";
      if (formulario.requestSubmit) formulario.requestSubmit(evento.submitter || undefined);
      else formulario.submit();
    };
    if (!dialogo || typeof dialogo.showModal !== "function") {
      if (window.confirm(mensaje)) enviar();
      return;
    }
    $("#confirmar-titulo").textContent = formulario.dataset.confirmarTitulo || "¿Seguro?";
    $("#confirmar-mensaje").textContent = mensaje;
    const aceptar = $("#confirmar-aceptar");
    aceptar.textContent = formulario.dataset.confirmarBoton || "Confirmar";
    aceptar.className = "boton " + (formulario.dataset.confirmarTipo === "peligro" ? "boton-peligro" : "boton-primario");
    dialogo.returnValue = "";
    dialogo.addEventListener("close", function alCerrar() {
      dialogo.removeEventListener("close", alCerrar);
      if (dialogo.returnValue === "si") enviar();
    });
    dialogo.showModal();
  });

  /* ---------- Copiar al portapapeles (<button data-copiar="id-del-campo">) ---------- */
  document.addEventListener("click", async (evento) => {
    const boton = evento.target.closest("[data-copiar]");
    if (!boton) return;
    const origen = document.getElementById(boton.dataset.copiar);
    if (!origen) return;
    const texto = origen.value !== undefined ? origen.value : origen.textContent;
    try {
      await navigator.clipboard.writeText(texto);
    } catch (error) {
      if (origen.select) { origen.select(); document.execCommand("copy"); }
    }
    const original = boton.dataset.textoOriginal || boton.textContent;
    boton.dataset.textoOriginal = original;
    boton.textContent = "¡Copiado!";
    setTimeout(() => { boton.textContent = original; }, 1800);
  });

  /* ---------- Cambiar tema y color sin recargar la página ---------- */
  function marcarApariencia(raiz) {
    const tema = raiz.dataset.tema;
    const acento = raiz.dataset.acento;
    $$("[data-pone-tema]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.poneTema === tema)));
    $$("[data-pone-acento]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.poneAcento === acento)));
  }
  $$("form.form-apariencia").forEach((formulario) => {
    formulario.addEventListener("submit", async (evento) => {
      if (!window.fetch) return;
      evento.preventDefault();
      try {
        const datos = new FormData(formulario, evento.submitter || undefined);
        const respuesta = await fetch(formulario.action, {
          method: "POST", body: datos, credentials: "same-origin",
          headers: { "X-Requested-With": "fetch", "X-CSRF-Token": token() },
        });
        if (!respuesta.ok) throw new Error("No se pudo guardar");
        const cambios = await respuesta.json();
        if (cambios.tema) document.documentElement.dataset.tema = cambios.tema;
        if (cambios.acento) document.documentElement.dataset.acento = cambios.acento;
        marcarApariencia(document.documentElement);
      } catch (error) {
        formulario.submit();  // si algo falla, que lo haga el servidor de la forma clásica
      }
    });
  });

  /* ---------- Montos con puntos de miles: 1200000 -> 1.200.000 ---------- */
  function formatearMonto(campo) {
    const posicion = campo.selectionStart == null ? campo.value.length : campo.selectionStart;
    const digitosAntes = campo.value.slice(0, posicion).replace(/\D/g, "").length;
    const digitos = campo.value.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
    const texto = digitos.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    if (texto === campo.value) return;
    campo.value = texto;
    let cuenta = 0, nueva = texto.length;
    if (digitosAntes === 0) nueva = 0;
    else {
      for (let i = 0; i < texto.length; i++) {
        if (/\d/.test(texto[i])) cuenta++;
        if (cuenta === digitosAntes) { nueva = i + 1; break; }
      }
    }
    try { campo.setSelectionRange(nueva, nueva); } catch (error) { /* algunos tipos de campo no lo permiten */ }
  }
  $$("input[data-monto]").forEach((campo) => {
    formatearMonto(campo);
    campo.addEventListener("input", () => formatearMonto(campo));
  });

  /* Lo comparten otras páginas (gasto.js, inicio.js) */
  window.SplitFacil = {
    pesos(numero) {
      const n = Math.round(Number(numero) || 0);
      return (n < 0 ? "-" : "") + "$" + String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    },
    numero(texto) { return parseInt(String(texto || "").replace(/\D/g, ""), 10) || 0; },
  };
})();
