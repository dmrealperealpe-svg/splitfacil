"""Perfil de usuario: datos, apariencia, contraseña, token de API y borrar cuenta."""
from flask import Blueprint, flash, g, redirect, render_template, session, url_for, request
from werkzeug.security import check_password_hash, generate_password_hash

from .. import datos, db, servicios
from ..seguridad import login_required
from ..utilidades import ACENTOS, EMOJIS_PERFIL, TEMAS, clave_invalida

bp = Blueprint("perfil", __name__)


@bp.route("/perfil")
@login_required
def ver():
    token_nuevo = session.pop("token_nuevo", None)  # se muestra una sola vez
    n_grupos = len(datos.grupos_de_usuario(g.user["id"]))
    return render_template("perfil/perfil.html", token_nuevo=token_nuevo, n_grupos=n_grupos)


@bp.post("/perfil/datos")
@login_required
def actualizar_datos():
    nombre = " ".join(request.form.get("nombre", "").split())
    bio = request.form.get("bio", "").strip()[:200]
    emoji = request.form.get("emoji", "")
    if len(nombre) < 2 or len(nombre) > 80:
        flash("Tu nombre debe tener entre 2 y 80 letras.", "error")
        return redirect(url_for("perfil.ver"))
    if emoji not in EMOJIS_PERFIL:
        emoji = ""
    datos.actualizar_usuario(g.user["id"], nombre=nombre, bio=bio, emoji=emoji)
    db.confirmar()
    flash("Guardamos los cambios de tu perfil.", "success")
    return redirect(url_for("perfil.ver"))


@bp.post("/perfil/apariencia")
@login_required
def actualizar_apariencia():
    tema = request.form.get("tema", "")
    acento = request.form.get("acento", "")
    if tema not in dict(TEMAS) or acento not in dict(ACENTOS):
        flash("Esa opción de apariencia no existe.", "error")
        return redirect(url_for("perfil.ver"))
    datos.actualizar_usuario(g.user["id"], tema=tema, acento=acento)
    db.confirmar()
    flash("Cambiamos la apariencia de la app.", "success")
    return redirect(url_for("perfil.ver"))


@bp.post("/perfil/clave")
@login_required
def cambiar_clave():
    actual = request.form.get("clave_actual", "")
    nueva = request.form.get("clave_nueva", "")
    nueva2 = request.form.get("clave_nueva2", "")
    if not check_password_hash(g.user["password_hash"], actual):
        flash("Tu contraseña actual no es correcta.", "error")
    elif clave_invalida(nueva):
        flash(clave_invalida(nueva), "error")
    elif nueva != nueva2:
        flash("Las contraseñas nuevas no coinciden.", "error")
    else:
        datos.actualizar_usuario(g.user["id"], password_hash=generate_password_hash(nueva))
        db.confirmar()
        flash("Cambiaste tu contraseña.", "success")
    return redirect(url_for("perfil.ver") + "#seguridad")


@bp.post("/perfil/token")
@login_required
def token_crear():
    session["token_nuevo"] = servicios.generar_token_api(g.user)
    flash("Creamos tu token de API. Cópialo ahora: no volverá a mostrarse.", "success")
    return redirect(url_for("perfil.ver") + "#api")


@bp.post("/perfil/token/revocar")
@login_required
def token_revocar():
    servicios.revocar_token_api(g.user)
    flash("Revocaste tu token de API.", "info")
    return redirect(url_for("perfil.ver") + "#api")


@bp.post("/perfil/eliminar")
@login_required
def eliminar():
    if not check_password_hash(g.user["password_hash"], request.form.get("clave", "")):
        flash("La contraseña no es correcta. No se eliminó nada.", "error")
        return redirect(url_for("perfil.ver") + "#peligro")
    if g.user["es_admin"] and datos.contar_admins() <= 1:
        flash("Eres el único administrador. Nombra a otro antes de eliminar tu cuenta.", "error")
        return redirect(url_for("perfil.ver") + "#peligro")
    servicios.eliminar_cuenta(g.user)
    session.clear()
    flash("Tu cuenta fue eliminada. Gracias por haber usado SplitFácil.", "info")
    return redirect(url_for("principal.inicio"))
