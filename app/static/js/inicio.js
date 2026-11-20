/* SplitFácil · inicio.js
   El "ticket" de la portada: escribes lo que costó la cuenta y cuántas personas son,
   y ves al instante cuánto paga cada una. Es la misma regla que usa la app de verdad. */
(function () {
  "use strict";
  const ticket = document.querySelector(".ticket");
  if (!ticket || !window.SplitFacil) return;
  const { pesos, numero } = window.SplitFacil;

  const monto = ticket.querySelector("#t-monto");
  const personas = ticket.querySelector("#t-personas");
  const cada = ticket.querySelector("#t-cada");
  const detalle = ticket.querySelector("#t-detalle");

  function limitar(n) { return Math.min(30, Math.max(2, n || 2)); }

  function actualizar() {
    const total = numero(monto.value);
    const n = limitar(parseInt(personas.value, 10));
    if (!total) {
      cada.textContent = "$0";
      detalle.textContent = "Escribe cuánto costó la cuenta.";
      return;
    }
    const base = Math.floor(total / n);
    const resto = total % n;
    cada.textContent = pesos(resto ? base + 1 : base);
    if (resto === 0) {
      detalle.textContent = "Cada una de las " + n + " personas paga lo mismo. Quien puso la plata recupera el resto.";
    } else {
      detalle.textContent = resto + (resto === 1 ? " persona paga " : " personas pagan ") + pesos(base + 1) +
        " y las otras " + pesos(base) + ". Así no se pierde ni un peso.";
    }
  }

  ticket.addEventListener("input", actualizar);
  ticket.addEventListener("click", (evento) => {
    const boton = evento.target.closest("[data-delta]");
    if (!boton) return;
    personas.value = limitar((parseInt(personas.value, 10) || 2) + parseInt(boton.dataset.delta, 10));
    actualizar();
  });
  personas.addEventListener("change", () => { personas.value = limitar(parseInt(personas.value, 10)); actualizar(); });
  actualizar();
})();
