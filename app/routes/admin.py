"""Panel de administración (Tema 5: roles y permisos).

Solo entra quien tiene `es_admin = 1`. Cualquier otra persona recibe un 403, aunque
escriba la dirección a mano (/admin/usuarios). El permiso se comprueba en el SERVIDOR
con @admin_required: esconder el botón en la pantalla no protege nada por sí solo.
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import datos, db, servicios
from ..seguridad import admin_required
from .grupos import Paginacion, numero_pagina

bp = Blueprint("admin", __name__, url_prefix="/admin")

POR_PAGINA = 12


def _usuario_o_404(usuario_id):
    usuario = datos.usuario_por_id(usuario_id)
    if usuario is None:
        abort(404)
    return usuario


def _volver(vista, **parametros):
    """Vuelve a la lista conservando la búsqueda y la página en la que estaba el administrador."""
    return redirect(url_for(vista, q=request.form.get("q") or None,
                            pagina=request.form.get("pagina") or None, **parametros))


# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------
@bp.route("/")
@admin_required
def panel():
    return render_template("admin/panel.html", stats=datos.estadisticas(),
                           recientes=datos.buscar_usuarios(limite=5),
                           mensajes=datos.listar_mensajes(limite=4))


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
@bp.route("/usuarios")
@admin_required
def usuarios():
    texto = request.args.get("q", "").strip()[:60]
    pagina = numero_pagina()
    total = datos.contar_usuarios(texto)
    filas = datos.buscar_usuarios(texto, POR_PAGINA, (pagina - 1) * POR_PAGINA)
    return render_template("admin/usuarios.html", usuarios=Paginacion(filas, total, pagina, POR_PAGINA), q=texto)


@bp.post("/usuarios/<int:usuario_id>/rol")
@admin_required
def cambiar_rol(usuario_id):
    usuario = _usuario_o_404(usuario_id)
    if usuario["id"] == g.user["id"]:
        flash("No puedes cambiar tu propio rol. Pídeselo a otro administrador.", "error")
    elif usuario["es_admin"] and datos.contar_admins() <= 1:
        flash("Debe quedar al menos un administrador.", "error")
    else:
        nuevo = 0 if usuario["es_admin"] else 1
        datos.actualizar_usuario(usuario_id, es_admin=nuevo)
        db.confirmar()
        flash(f"{usuario['nombre']} ahora es {'administrador/a' if nuevo else 'usuario/a normal'}.", "success")
    return _volver("admin.usuarios")


@bp.post("/usuarios/<int:usuario_id>/activo")
@admin_required
def cambiar_activo(usuario_id):
    usuario = _usuario_o_404(usuario_id)
    if usuario["id"] == g.user["id"]:
        flash("No puedes desactivar tu propia cuenta desde aquí.", "error")
    elif usuario["es_admin"] and usuario["activo"] and datos.contar_admins() <= 1:
        flash("Debe quedar al menos un administrador activo.", "error")
    else:
        nuevo = 0 if usuario["activo"] else 1
        datos.actualizar_usuario(usuario_id, activo=nuevo)
        db.confirmar()
        flash(f"La cuenta de {usuario['nombre']} quedó {'activa' if nuevo else 'desactivada'}.",
              "success" if nuevo else "info")
    return _volver("admin.usuarios")


@bp.post("/usuarios/<int:usuario_id>/eliminar")
@admin_required
def eliminar_usuario(usuario_id):
    usuario = _usuario_o_404(usuario_id)
    if usuario["id"] == g.user["id"]:
        flash("Para borrar tu propia cuenta usa tu perfil.", "error")
    elif usuario["es_admin"] and datos.contar_admins() <= 1:
        flash("No puedes borrar al único administrador.", "error")
    else:
        servicios.eliminar_cuenta(usuario)
        flash(f"Eliminaste la cuenta de {usuario['nombre']}.", "info")
    return _volver("admin.usuarios")


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------
@bp.route("/grupos")
@admin_required
def grupos():
    texto = request.args.get("q", "").strip()[:60]
    pagina = numero_pagina()
    total = datos.contar_grupos(texto)
    filas = datos.buscar_grupos(texto, POR_PAGINA, (pagina - 1) * POR_PAGINA)
    return render_template("admin/grupos.html", grupos=Paginacion(filas, total, pagina, POR_PAGINA), q=texto)


@bp.post("/grupos/<int:grupo_id>/eliminar")
@admin_required
def eliminar_grupo(grupo_id):
    grupo = datos.grupo_por_id(grupo_id)
    if grupo is None:
        abort(404)
    datos.borrar_grupo(grupo_id)
    db.confirmar()
    flash(f"Eliminaste el grupo «{grupo['nombre']}».", "info")
    return _volver("admin.grupos")


# ---------------------------------------------------------------------------
# Mensajes del formulario de contacto
# ---------------------------------------------------------------------------
@bp.route("/mensajes")
@admin_required
def mensajes():
    pagina = numero_pagina()
    filas = datos.listar_mensajes(POR_PAGINA, (pagina - 1) * POR_PAGINA)
    return render_template("admin/mensajes.html",
                           mensajes=Paginacion(filas, datos.contar_mensajes(), pagina, POR_PAGINA))


@bp.post("/mensajes/<int:mensaje_id>/leido")
@admin_required
def marcar_leido(mensaje_id):
    datos.marcar_mensaje(mensaje_id, request.form.get("leido") == "1")
    db.confirmar()
    return _volver("admin.mensajes")


@bp.post("/mensajes/<int:mensaje_id>/eliminar")
@admin_required
def eliminar_mensaje(mensaje_id):
    datos.borrar_mensaje(mensaje_id)
    db.confirmar()
    flash("Eliminaste el mensaje.", "info")
    return _volver("admin.mensajes")
