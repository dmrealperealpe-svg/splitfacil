/* SplitFácil · gasto.js
   Formulario de gastos: muestra al instante cuánto le toca a cada persona y,
   si el reparto es "exacto", comprueba que las partes sumen el total.
   (El servidor vuelve a validar todo: esto es solo ayuda visual.) */
(function () {
  "use strict";
  const formulario = document.querySelector(".formulario-gasto");
  if (!formulario || !window.SplitFacil) return;
  const { pesos, numero } = window.SplitFacil;

  const monto = formulario.querySelector("#monto");
  const filas = Array.from(formulario.querySelectorAll(".participante"));
  const radioExacta = formulario.querySelector("#division-exacta");
  const control = formulario.querySelector(".suma-control");

  const idDe = (fila) => parseInt(fila.dataset.miembro, 10);
  const marcada = (fila) => fila.querySelector('input[type="checkbox"]').checked;

  /* Misma regla que el servidor: se reparte sin perder ni un peso (100 entre 3 -> 34, 33, 33) */
  function partesIguales(total, ids) {
    const ordenados = ids.slice().sort((a, b) => a - b);
    const base = Math.floor(total / ordenados.length);
    const resto = total % ordenados.length;
    const partes = {};
    ordenados.forEach((id, i) => { partes[id] = base + (i < resto ? 1 : 0); });
    return partes;
  }

  function actualizar() {
    const total = numero(monto.value);
    const elegidas = filas.filter(marcada).map(idDe);
    const partes = total && elegidas.length ? partesIguales(total, elegidas) : {};

    filas.forEach((fila) => {
      const previa = fila.querySelector(".parte-previa");
      previa.textContent = marcada(fila) && total ? pesos(partes[idDe(fila)]) : "—";
    });

    if (radioExacta && radioExacta.checked && control) {
      let suma = 0;
      filas.forEach((fila) => {
        const campo = fila.querySelector("input[data-parte]");
        if (marcada(fila)) suma += numero(campo.value);
      });
      const diferencia = total - suma;
      control.classList.toggle("ok", total > 0 && diferencia === 0);
      control.classList.toggle("mal", !(total > 0 && diferencia === 0));
      if (!total) control.textContent = "Escribe primero el monto del gasto.";
      else if (diferencia === 0) control.textContent = "Perfecto: las partes suman " + pesos(total) + ".";
      else if (diferencia > 0) control.textContent = "Suman " + pesos(suma) + " de " + pesos(total) + ". Faltan " + pesos(diferencia) + ".";
      else control.textContent = "Suman " + pesos(suma) + " y el gasto es de " + pesos(total) + ". Sobran " + pesos(-diferencia) + ".";
    }
  }

  formulario.addEventListener("input", actualizar);
  formulario.addEventListener("change", actualizar);

  /* Atajos: marcar a todos / a nadie, y llenar las partes con el reparto igual */
  formulario.addEventListener("click", (evento) => {
    const atajo = evento.target.closest("[data-marcar]");
    if (atajo) {
      filas.forEach((fila) => { fila.querySelector('input[type="checkbox"]').checked = atajo.dataset.marcar === "todos"; });
      actualizar();
    }
    if (evento.target.closest("[data-autocompletar]")) {
      const total = numero(monto.value);
      const elegidas = filas.filter(marcada).map(idDe);
      if (!total || !elegidas.length) return;
      const partes = partesIguales(total, elegidas);
      filas.forEach((fila) => {
        const campo = fila.querySelector("input[data-parte]");
        campo.value = marcada(fila) ? pesos(partes[idDe(fila)]).replace("$", "") : "";
      });
      actualizar();
    }
  });

  actualizar();
})();
