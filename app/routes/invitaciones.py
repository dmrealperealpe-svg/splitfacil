"""Invitar a otras personas a un grupo: por correo (bandeja) o por enlace."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import datos, servicios
from ..seguridad import login_required, url_segura

bp = Blueprint("invitaciones", __name__)


def _cargar_grupo(grupo_id):
    grupo = datos.grupo_por_id(grupo_id)
    if grupo is None:
        abort(404)
    if datos.miembro_de_usuario(grupo_id, g.user["id"]) is None:
        abort(403)
    return grupo


@bp.post("/grupos/<int:grupo_id>/invitar")
@login_required
def invitar(grupo_id):
    grupo = _cargar_grupo(grupo_id)
    miembros = datos.miembros_de_grupo(grupo_id)
    try:
        miembro_id = int(request.form.get("miembro_id", "")) if request.form.get("miembro_id") else None
    except ValueError:
        miembro_id = -1
    invitacion, error = servicios.crear_invitacion(grupo, g.user, request.form.get("email", ""), miembro_id, miembros)
    if error:
        flash(error, "error")
    elif invitacion["email"]:
        flash(f"Invitaste a {invitacion['email']}. Le aparecerá en su bandeja de invitaciones "
              "cuando entre a SplitFácil. También puedes copiar el enlace de abajo.", "success")
    else:
        flash("Creamos un enlace de invitación. Cópialo y compártelo por WhatsApp o donde quieras.", "success")
    return redirect(url_for("grupos.detalle", grupo_id=grupo_id, vista="personas") + "#invitar")


@bp.post("/invitaciones/<int:invitacion_id>/cancelar")
@login_required
def cancelar(invitacion_id):
    invitacion = datos.invitacion_por_id(invitacion_id)
    if invitacion is None:
        abort(404)
    _cargar_grupo(invitacion["grupo_id"])
    if invitacion["estado"] == "pendiente":
        servicios.cerrar_invitacion(invitacion, "cancelada")
        flash("Cancelaste la invitación.", "info")
    return redirect(url_for("grupos.detalle", grupo_id=invitacion["grupo_id"], vista="personas") + "#invitar")


@bp.route("/invitaciones")
@login_required
def bandeja():
    pendientes = datos.invitaciones_de_email(g.user["email"], estado="pendiente")
    historial = datos.invitaciones_de_email(g.user["email"], limite=10)
    return render_template("invitaciones/bandeja.html", pendientes=pendientes, historial=historial)


def _responder(invitacion_id, aceptar):
    invitacion = datos.invitacion_por_id(invitacion_id)
    if invitacion is None:
        abort(404)
    if not servicios.puede_responder(invitacion, g.user) or invitacion["email"] is None:
        abort(403)  # solo el dueño del correo invitado responde desde la bandeja
    if invitacion["estado"] != "pendiente":
        flash("Esa invitación ya no está disponible.", "warning")
        return redirect(url_for("invitaciones.bandeja"))
    if aceptar:
        servicios.aceptar_invitacion(invitacion, g.user)
        flash(f"¡Listo! Ahora eres parte de «{invitacion['grupo_nombre']}».", "success")
        return redirect(url_for("grupos.detalle", grupo_id=invitacion["grupo_id"]))
    servicios.cerrar_invitacion(invitacion, "rechazada")
    flash("Rechazaste la invitación.", "info")
    return redirect(url_for("invitaciones.bandeja"))


@bp.post("/invitaciones/<int:invitacion_id>/aceptar")
@login_required
def aceptar(invitacion_id):
    return _responder(invitacion_id, True)


@bp.post("/invitaciones/<int:invitacion_id>/rechazar")
@login_required
def rechazar(invitacion_id):
    return _responder(invitacion_id, False)


@bp.route("/unirse/<token>", methods=["GET", "POST"])
def unirse(token):
    """Enlace de invitación: quien lo abre inicia sesión (o se registra) y se une al grupo."""
    invitacion = datos.invitacion_por_token(token)
    if invitacion is None:
        abort(404)
    if g.user is None:
        flash("Inicia sesión o crea tu cuenta para unirte al grupo.", "info")
        return redirect(url_for("auth.entrar", next=url_segura(request.path)))
    if invitacion["estado"] != "pendiente":
        return render_template("invitaciones/unirse.html", invitacion=invitacion, estado="cerrada")
    if not servicios.puede_responder(invitacion, g.user):
        return render_template("invitaciones/unirse.html", invitacion=invitacion, estado="otro_correo")
    if request.method == "POST":
        if request.form.get("accion") == "rechazar":
            servicios.cerrar_invitacion(invitacion, "rechazada")
            flash("Rechazaste la invitación.", "info")
            return redirect(url_for("grupos.panel"))
        servicios.aceptar_invitacion(invitacion, g.user)
        flash(f"¡Listo! Ahora eres parte de «{invitacion['grupo_nombre']}».", "success")
        return redirect(url_for("grupos.detalle", grupo_id=invitacion["grupo_id"]))
    return render_template("invitaciones/unirse.html", invitacion=invitacion, estado="pendiente")
