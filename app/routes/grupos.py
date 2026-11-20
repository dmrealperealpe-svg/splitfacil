"""Panel, grupos, miembros, gastos y pagos (el corazón de SplitFácil)."""
import csv
import io

from flask import (Blueprint, Response, abort, flash, g, redirect, render_template,
                   request, url_for)

from .. import datos, db, servicios
from ..seguridad import login_required
from ..utilidades import CATEGORIAS, EMOJIS_GRUPO, cop, hoy_local, seguro_csv, slug

bp = Blueprint("grupos", __name__)

POR_PAGINA = 12


class Paginacion:
    """Lo mínimo para paginar listas: página actual, total de páginas y vecinas."""

    def __init__(self, items, total, pagina, por_pagina):
        self.items, self.total, self.pagina = items, total, pagina
        self.paginas = max(1, -(-total // por_pagina))
        self.hay_anterior, self.hay_siguiente = pagina > 1, pagina < self.paginas


def numero_pagina():
    try:
        return max(1, int(request.args.get("pagina", 1)))
    except ValueError:
        return 1


def cargar_grupo(grupo_id):
    """Devuelve (grupo, mi_membresia). 404 si no existe; 403 si no eres parte del grupo."""
    grupo = datos.grupo_por_id(grupo_id)
    if grupo is None:
        abort(404)
    yo = datos.miembro_de_usuario(grupo_id, g.user["id"])
    if yo is None:
        abort(403)
    return grupo, yo


def solo_propietario(yo):
    if not yo["es_propietario"]:
        abort(403)


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
@bp.route("/panel")
@login_required
def panel():
    tarjetas, te_deben, debes = servicios.resumen_usuario(g.user["id"])
    actividad = datos.actividad_reciente([t["id"] for t in tarjetas], limite=8)
    pendientes = datos.invitaciones_de_email(g.user["email"], estado="pendiente")
    return render_template("grupos/panel.html", grupos=tarjetas, te_deben=te_deben, debes=debes,
                           actividad=actividad, pendientes=pendientes)


@bp.post("/panel/ejemplo")
@login_required
def ejemplo():
    servicios.crear_datos_demo(g.user)
    flash("Cargamos dos grupos de ejemplo. Puedes borrarlos cuando quieras.", "success")
    return redirect(url_for("grupos.panel"))


# ---------------------------------------------------------------------------
# Crear, editar y eliminar grupos
# ---------------------------------------------------------------------------
@bp.route("/grupos/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    valores, errores = {"emoji": EMOJIS_GRUPO[0]}, {}
    if request.method == "POST":
        campos, errores = servicios.validar_grupo(request.form, EMOJIS_GRUPO)
        valores = {**campos, "invitados": request.form.get("invitados", "")}
        if not errores:
            grupo_id = servicios.crear_grupo(g.user, campos, valores["invitados"])
            flash(f"Creaste el grupo «{campos['nombre']}». ¡Ahora agrega el primer gasto!", "success")
            return redirect(url_for("grupos.detalle", grupo_id=grupo_id))
        flash("Revisa los campos marcados en rojo.", "error")
    return render_template("grupos/nuevo.html", valores=valores, errores=errores)


@bp.route("/grupos/<int:grupo_id>/editar", methods=["GET", "POST"])
@login_required
def editar(grupo_id):
    grupo, yo = cargar_grupo(grupo_id)
    solo_propietario(yo)
    valores, errores = dict(grupo), {}
    if request.method == "POST":
        campos, errores = servicios.validar_grupo(request.form, EMOJIS_GRUPO)
        valores = campos
        if not errores:
            datos.actualizar_grupo(grupo_id, campos["nombre"], campos["descripcion"], campos["emoji"])
            servicios.registrar(grupo_id, g.user, "actualizó los datos del grupo")
            db.confirmar()
            flash("Guardamos los cambios del grupo.", "success")
            return redirect(url_for("grupos.detalle", grupo_id=grupo_id))
        flash("Revisa los campos marcados en rojo.", "error")
    return render_template("grupos/editar.html", grupo=grupo, valores=valores, errores=errores)


@bp.post("/grupos/<int:grupo_id>/eliminar")
@login_required
def eliminar(grupo_id):
    grupo, yo = cargar_grupo(grupo_id)
    solo_propietario(yo)
    datos.borrar_grupo(grupo_id)
    db.confirmar()
    flash(f"Eliminaste el grupo «{grupo['nombre']}» con todos sus gastos.", "info")
    return redirect(url_for("grupos.panel"))


# ---------------------------------------------------------------------------
# Detalle del grupo (pestañas: gastos, saldos, personas, historial)
# ---------------------------------------------------------------------------
@bp.route("/grupos/<int:grupo_id>")
@login_required
def detalle(grupo_id):
    grupo, yo = cargar_grupo(grupo_id)
    vista = request.args.get("vista", "gastos")
    if vista not in ("gastos", "saldos", "personas", "chat", "historial"):
        vista = "gastos"

    miembros = datos.miembros_de_grupo(grupo_id)
    por_id = {m["id"]: m for m in miembros}
    saldos = servicios.saldos(grupo_id, miembros)
    sugeridos = [{"de": por_id[d], "a": por_id[a], "monto": monto}
                 for d, a, monto in servicios.deudas_sugeridas(saldos)]
    contexto = dict(grupo=grupo, yo=yo, vista=vista, miembros=miembros, saldos=saldos, sugeridos=sugeridos,
                    mi_saldo=saldos.get(yo["id"], 0), total=datos.total_gastado(grupo_id),
                    n_gastos=datos.contar_gastos(grupo_id), soy_propietario=bool(yo["es_propietario"]))

    if vista == "gastos":
        texto = request.args.get("q", "").strip()[:60]
        categoria = request.args.get("categoria", "")
        if categoria not in CATEGORIAS:
            categoria = ""
        pagina = numero_pagina()
        total = datos.contar_gastos(grupo_id, texto, categoria)
        filas = datos.gastos_de_grupo(grupo_id, yo["id"], texto, categoria, POR_PAGINA, (pagina - 1) * POR_PAGINA)
        for fila in filas:
            fila["puedo_editar"] = servicios.puede_modificar(fila, g.user, yo)
        contexto.update(gastos=Paginacion(filas, total, pagina, POR_PAGINA), q=texto, categoria=categoria)
    elif vista == "saldos":
        pagos = datos.pagos_de_grupo(grupo_id)
        for pago in pagos:
            pago["puedo_borrar"] = servicios.puede_modificar(pago, g.user, yo)
        contexto.update(pagos=pagos, categorias=servicios.resumen_por_categoria(grupo_id),
                        max_saldo=max([abs(s) for s in saldos.values()] + [1]))
    elif vista == "personas":
        contexto.update(
            invitaciones=datos.invitaciones_pendientes_de_grupo(grupo_id),
            invitados_sin_cuenta=[m for m in miembros if not m["tiene_cuenta"]])
    elif vista == "chat":
        mensajes = datos.mensajes_de_chat(grupo_id)
        for m in mensajes:
            m["puedo_borrar"] = _puede_borrar_comentario(m, yo)
        contexto.update(mensajes=mensajes, errores={}, texto="")
    else:
        contexto.update(actividad=datos.actividad_de_grupo(grupo_id))
    return render_template("grupos/detalle.html", **contexto)


# ---------------------------------------------------------------------------
# Chat del grupo y comentarios en gastos
# ---------------------------------------------------------------------------
MAX_COMENTARIO = 500


def _puede_borrar_comentario(comentario, yo):
    return comentario["usuario_id"] == g.user["id"] or bool(yo["es_propietario"])


def _texto_comentario():
    texto = "\n".join(linea.rstrip() for linea in request.form.get("texto", "").strip().splitlines())
    if not texto:
        return None, "Escribe algo antes de enviar."
    if len(texto) > MAX_COMENTARIO:
        return texto, f"El mensaje es muy largo (máximo {MAX_COMENTARIO} letras)."
    return texto, None


@bp.post("/grupos/<int:grupo_id>/chat")
@login_required
def chat_enviar(grupo_id):
    cargar_grupo(grupo_id)
    texto, error = _texto_comentario()
    if error:
        flash(error, "error")
    else:
        datos.crear_comentario(grupo_id, g.user["id"], texto)
        db.confirmar()
    return redirect(url_for("grupos.detalle", grupo_id=grupo_id, vista="chat") + "#escribir")


@bp.route("/grupos/<int:grupo_id>/gastos/<int:gasto_id>")
@login_required
def gasto_ver(grupo_id, gasto_id):
    grupo, yo = cargar_grupo(grupo_id)
    gasto = datos.gasto_por_id(gasto_id)
    if gasto is None or gasto["grupo_id"] != grupo_id:
        abort(404)
    miembros = datos.miembros_de_grupo(grupo_id)
    por_id = {m["id"]: m for m in miembros}
    partes = [{"miembro": por_id[mid], "monto": monto}
              for mid, monto in datos.participaciones_de_gasto(gasto_id).items() if mid in por_id]
    comentarios = datos.comentarios_de_gasto(gasto_id)
    for c in comentarios:
        c["puedo_borrar"] = _puede_borrar_comentario(c, yo)
    return render_template("grupos/gasto_ver.html", grupo=grupo, gasto=gasto, yo=yo,
                           pagador=por_id.get(gasto["pagado_por_id"]), partes=partes,
                           comentarios=comentarios, puedo_editar=servicios.puede_modificar(gasto, g.user, yo))


@bp.post("/grupos/<int:grupo_id>/gastos/<int:gasto_id>/comentarios")
@login_required
def comentar_gasto(grupo_id, gasto_id):
    grupo, yo = cargar_grupo(grupo_id)
    gasto = datos.gasto_por_id(gasto_id)
    if gasto is None or gasto["grupo_id"] != grupo_id:
        abort(404)
    texto, error = _texto_comentario()
    if error:
        flash(error, "error")
    else:
        datos.crear_comentario(grupo_id, g.user["id"], texto, gasto_id)
        servicios.registrar(grupo_id, g.user, f"comentó en «{gasto['descripcion']}»")
        db.confirmar()
        flash("Comentario publicado.", "success")
    return redirect(url_for("grupos.gasto_ver", grupo_id=grupo_id, gasto_id=gasto_id) + "#comentarios")


@bp.post("/grupos/<int:grupo_id>/comentarios/<int:comentario_id>/eliminar")
@login_required
def comentario_eliminar(grupo_id, comentario_id):
    grupo, yo = cargar_grupo(grupo_id)
    comentario = datos.comentario_por_id(comentario_id)
    if comentario is None or comentario["grupo_id"] != grupo_id:
        abort(404)
    if not _puede_borrar_comentario(comentario, yo):
        abort(403)
    datos.borrar_comentario(comentario_id)
    db.confirmar()
    flash("Mensaje eliminado.", "info")
    if comentario["gasto_id"]:
        return redirect(url_for("grupos.gasto_ver", grupo_id=grupo_id, gasto_id=comentario["gasto_id"]) + "#comentarios")
    return redirect(url_for("grupos.detalle", grupo_id=grupo_id, vista="chat"))


# ---------------------------------------------------------------------------
# Personas del grupo
# ---------------------------------------------------------------------------
@bp.post("/grupos/<int:grupo_id>/invitados")
@login_required
def invitado_nuevo(grupo_id):
    grupo, _yo = cargar_grupo(grupo_id)
    ok, mensaje = servicios.agregar_invitado(grupo, g.user, request.form.get("nombre", ""))
    flash(mensaje, "success" if ok else "error")
    return redirect(url_for("grupos.detalle", grupo_id=grupo_id, vista="personas"))


@bp.post("/grupos/<int:grupo_id>/miembros/<int:miembro_id>/quitar")
@login_required
def quitar_miembro(grupo_id, miembro_id):
    grupo, yo = cargar_grupo(grupo_id)
    solo_propietario(yo)
    miembro = datos.miembro_por_id(miembro_id)
    if miembro is None or miembro["grupo_id"] != grupo_id:
        abort(404)
    ok, mensaje = servicios.quitar_miembro(grupo, miembro, g.user)
    flash(mensaje, "success" if ok else "error")
    return redirect(url_for("grupos.detalle", grupo_id=grupo_id, vista="personas"))


@bp.post("/grupos/<int:grupo_id>/miembros/<int:miembro_id>/propietario")
@login_required
def propietario(grupo_id, miembro_id):
    grupo, yo = cargar_grupo(grupo_id)
    solo_propietario(yo)
    destino = datos.miembro_por_id(miembro_id)
    if destino is None or destino["grupo_id"] != grupo_id:
        abort(404)
    ok, mensaje = servicios.transferir_propiedad(grupo, yo, destino, g.user)
    flash(mensaje, "success" if ok else "error")
    return redirect(url_for("grupos.detalle", grupo_id=grupo_id, vista="personas"))


@bp.post("/grupos/<int:grupo_id>/salir")
@login_required
def salir(grupo_id):
    grupo, yo = cargar_grupo(grupo_id)
    ok, mensaje = servicios.salir_del_grupo(grupo, yo, g.user)
    flash(mensaje, "success" if ok else "error")
    if ok:
        return redirect(url_for("grupos.panel"))
    return redirect(url_for("grupos.detalle", grupo_id=grupo_id, vista="personas"))


# ---------------------------------------------------------------------------
# Gastos
# ---------------------------------------------------------------------------
def _valores_gasto(gasto, miembros):
    """Convierte un gasto guardado en los valores que muestra el formulario de edición."""
    partes = datos.participaciones_de_gasto(gasto["id"])
    return {"descripcion": gasto["descripcion"], "monto": str(gasto["monto"]), "categoria": gasto["categoria"],
            "fecha": gasto["fecha"], "pagado_por": gasto["pagado_por_id"], "tipo_division": gasto["tipo_division"],
            "participantes": list(partes), "partes": partes, "nota": gasto["nota"]}


@bp.route("/grupos/<int:grupo_id>/gastos/nuevo", methods=["GET", "POST"])
@login_required
def gasto_nuevo(grupo_id):
    grupo, yo = cargar_grupo(grupo_id)
    miembros = datos.miembros_de_grupo(grupo_id)
    valores = {"fecha": hoy_local(), "categoria": "comida", "pagado_por": yo["id"], "tipo_division": "igual",
               "participantes": [m["id"] for m in miembros], "partes": {}}
    errores = {}
    if request.method == "POST":
        campos, errores = servicios.validar_gasto(miembros, request.form)
        valores = {**campos, "monto": request.form.get("monto", ""),
                   "partes_texto": {m["id"]: request.form.get(f"parte_{m['id']}", "") for m in miembros}}
        if not errores:
            servicios.guardar_gasto(grupo, g.user, campos)
            flash(f"Agregaste «{campos['descripcion']}» por {cop(campos['monto'])}.", "success")
            return redirect(url_for("grupos.detalle", grupo_id=grupo_id))
        flash("Revisa los campos marcados en rojo.", "error")
    return render_template("grupos/gasto_form.html", grupo=grupo, miembros=miembros, valores=valores,
                           errores=errores, gasto=None)


@bp.route("/grupos/<int:grupo_id>/gastos/<int:gasto_id>/editar", methods=["GET", "POST"])
@login_required
def gasto_editar(grupo_id, gasto_id):
    grupo, yo = cargar_grupo(grupo_id)
    gasto = datos.gasto_por_id(gasto_id)
    if gasto is None or gasto["grupo_id"] != grupo_id:
        abort(404)
    if not servicios.puede_modificar(gasto, g.user, yo):
        abort(403)
    miembros = datos.miembros_de_grupo(grupo_id)
    valores, errores = _valores_gasto(gasto, miembros), {}
    if request.method == "POST":
        campos, errores = servicios.validar_gasto(miembros, request.form)
        valores = {**campos, "monto": request.form.get("monto", ""),
                   "partes_texto": {m["id"]: request.form.get(f"parte_{m['id']}", "") for m in miembros}}
        if not errores:
            servicios.guardar_gasto(grupo, g.user, campos, gasto_id)
            flash("Guardamos los cambios del gasto.", "success")
            return redirect(url_for("grupos.detalle", grupo_id=grupo_id))
        flash("Revisa los campos marcados en rojo.", "error")
    return render_template("grupos/gasto_form.html", grupo=grupo, miembros=miembros, valores=valores,
                           errores=errores, gasto=gasto)


@bp.post("/grupos/<int:grupo_id>/gastos/<int:gasto_id>/eliminar")
@login_required
def gasto_eliminar(grupo_id, gasto_id):
    grupo, yo = cargar_grupo(grupo_id)
    gasto = datos.gasto_por_id(gasto_id)
    if gasto is None or gasto["grupo_id"] != grupo_id:
        abort(404)
    if not servicios.puede_modificar(gasto, g.user, yo):
        abort(403)
    datos.borrar_gasto(gasto_id)
    servicios.registrar(grupo_id, g.user, f"eliminó el gasto «{gasto['descripcion']}» ({cop(gasto['monto'])})")
    db.confirmar()
    flash(f"Eliminaste el gasto «{gasto['descripcion']}».", "info")
    return redirect(url_for("grupos.detalle", grupo_id=grupo_id))


# ---------------------------------------------------------------------------
# Pagos (saldar deudas)
# ---------------------------------------------------------------------------
@bp.route("/grupos/<int:grupo_id>/pagos/nuevo", methods=["GET", "POST"])
@login_required
def pago_nuevo(grupo_id):
    grupo, yo = cargar_grupo(grupo_id)
    miembros = datos.miembros_de_grupo(grupo_id)
    valores = {"fecha": hoy_local(), "de": request.args.get("de", yo["id"]), "a": request.args.get("a", ""),
               "monto": request.args.get("monto", ""), "nota": ""}
    errores = {}
    if request.method == "POST":
        campos, errores = servicios.validar_pago(miembros, request.form)
        valores = {**campos, "monto": request.form.get("monto", "")}
        if not errores:
            servicios.guardar_pago(grupo, g.user, campos, miembros)
            flash(f"Registraste el pago de {cop(campos['monto'])}.", "success")
            return redirect(url_for("grupos.detalle", grupo_id=grupo_id, vista="saldos"))
        flash("Revisa los campos marcados en rojo.", "error")
    return render_template("grupos/pago_form.html", grupo=grupo, miembros=miembros, valores=valores, errores=errores)


@bp.post("/grupos/<int:grupo_id>/pagos/<int:pago_id>/eliminar")
@login_required
def pago_eliminar(grupo_id, pago_id):
    grupo, yo = cargar_grupo(grupo_id)
    pago = datos.pago_por_id(pago_id)
    if pago is None or pago["grupo_id"] != grupo_id:
        abort(404)
    if not servicios.puede_modificar(pago, g.user, yo):
        abort(403)
    datos.borrar_pago(pago_id)
    servicios.registrar(grupo_id, g.user, f"eliminó un pago de {cop(pago['monto'])}")
    db.confirmar()
    flash("Eliminaste el pago.", "info")
    return redirect(url_for("grupos.detalle", grupo_id=grupo_id, vista="saldos"))


# ---------------------------------------------------------------------------
# Exportar a CSV (se abre directo en Excel)
# ---------------------------------------------------------------------------
@bp.route("/grupos/<int:grupo_id>/exportar.csv")
@login_required
def exportar(grupo_id):
    grupo, _yo = cargar_grupo(grupo_id)
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(["Fecha", "Descripción", "Categoría", "Pagó", "Monto (COP)", "División", "Reparto", "Nota"])
    for gasto in datos.gastos_para_exportar(grupo_id):
        reparto = " | ".join(f"{p['nombre']}: {p['monto']}" for p in gasto["partes"])
        escritor.writerow([gasto["fecha"], seguro_csv(gasto["descripcion"]),
                           CATEGORIAS.get(gasto["categoria"], CATEGORIAS["otros"])[0],
                           seguro_csv(gasto["pagador"]), gasto["monto"], gasto["tipo_division"],
                           seguro_csv(reparto), seguro_csv(gasto["nota"])])
    # El BOM (﻿) hace que Excel muestre bien las tildes y la ñ.
    return Response("﻿" + salida.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="gastos-{slug(grupo["nombre"])}.csv"'})
