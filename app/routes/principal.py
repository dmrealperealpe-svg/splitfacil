"""Páginas públicas: inicio, ayuda, contacto y preferencias de apariencia."""
from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from .. import datos, db
from ..seguridad import volver_a
from ..utilidades import ACENTOS, TEMAS, email_valido

bp = Blueprint("principal", __name__)


@bp.route("/")
def inicio():
    if g.user:
        return redirect(url_for("grupos.panel"))
    return render_template("principal/inicio.html")


@bp.route("/ayuda")
def ayuda():
    return render_template("principal/ayuda.html")


@bp.route("/desarrolladores")
def desarrolladores():
    """Documentación de la API para quien quiera conectarse a SplitFácil."""
    return render_template("principal/desarrolladores.html")


@bp.route("/contacto", methods=["GET", "POST"])
def contacto():
    valores, errores = {}, {}
    if g.user:
        valores = {"nombre": g.user["nombre"], "email": g.user["email"]}
    if request.method == "POST":
        nombre = " ".join(request.form.get("nombre", "").split())
        email = request.form.get("email", "").strip().lower()
        texto = request.form.get("texto", "").strip()
        valores = {"nombre": nombre, "email": email, "texto": texto}
        if len(nombre) < 2:
            errores["nombre"] = "Escribe tu nombre."
        if not email_valido(email):
            errores["email"] = "Escribe un correo válido para poder responderte."
        if len(texto) < 10:
            errores["texto"] = "Cuéntanos un poco más (mínimo 10 letras)."
        elif len(texto) > 1000:
            errores["texto"] = "El mensaje es muy largo (máximo 1000 letras)."
        if not errores:
            datos.crear_mensaje(nombre[:80], email, texto)
            db.confirmar()
            flash("¡Gracias! Recibimos tu mensaje y te responderemos pronto.", "success")
            return redirect(url_for("principal.contacto"))  # Post-Redirect-Get: evita reenviar al recargar
        flash("Revisa los campos marcados en rojo.", "error")
    return render_template("principal/contacto.html", valores=valores, errores=errores)


@bp.post("/preferencias")
def preferencias():
    """Guarda tema (claro/oscuro/automático) y color de acento. Funciona con o sin cuenta."""
    tema = request.form.get("tema", "")
    acento = request.form.get("acento", "")
    cambios = {}
    if tema in dict(TEMAS):
        cambios["tema"] = tema
    if acento in dict(ACENTOS):
        cambios["acento"] = acento
    if not cambios:
        abort(400)
    if g.user:
        datos.actualizar_usuario(g.user["id"], **cambios)
        db.confirmar()
    if request.headers.get("X-Requested-With") == "fetch":
        respuesta = jsonify(ok=True, **cambios)
    else:
        respuesta = redirect(volver_a(url_for("principal.inicio")))
    for nombre, valor in cambios.items():  # sin cuenta, la preferencia se recuerda en una cookie
        respuesta.set_cookie(nombre, valor, max_age=365 * 24 * 3600, samesite="Lax",
                             secure=current_app.config["SESSION_COOKIE_SECURE"])
    return respuesta
