"""Registro, inicio y cierre de sesión, y recuperación de contraseña (Tema 5)."""
from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .. import correo, datos, db, seguridad
from ..utilidades import ahora, clave_invalida, email_valido

bp = Blueprint("auth", __name__)

# Se compara contra este hash cuando el correo no existe, para que la respuesta
# tarde lo mismo y nadie pueda adivinar qué correos están registrados.
_HASH_FALSO = generate_password_hash("clave-falsa-para-igualar-tiempos")


def _entrar(usuario, recordar=False):
    seguridad.iniciar_sesion(usuario, recordar)
    datos.actualizar_usuario(usuario["id"], ultimo_acceso=ahora())
    db.confirmar()


@bp.route("/registro", methods=["GET", "POST"])
def registro():
    if g.user:
        return redirect(url_for("grupos.panel"))
    destino = request.values.get("next", "")
    valores, errores = {}, {}
    if request.method == "POST":
        nombre = " ".join(request.form.get("nombre", "").split())
        email = request.form.get("email", "").strip().lower()
        clave = request.form.get("clave", "")
        clave2 = request.form.get("clave2", "")
        valores = {"nombre": nombre, "email": email}

        if len(nombre) < 2:
            errores["nombre"] = "Escribe tu nombre (mínimo 2 letras)."
        elif len(nombre) > 80:
            errores["nombre"] = "El nombre es demasiado largo."
        if not email_valido(email):
            errores["email"] = "Escribe un correo válido."
        elif datos.usuario_por_email(email):
            errores["email"] = "Ya existe una cuenta con ese correo. ¿Quieres iniciar sesión?"
        problema = clave_invalida(clave)
        if problema:
            errores["clave"] = problema
        elif clave != clave2:
            errores["clave2"] = "Las contraseñas no coinciden."

        if not errores:
            admin_email = current_app.config["ADMIN_EMAIL"]
            es_admin = bool(admin_email) and email == admin_email
            usuario_id = datos.crear_usuario(nombre, email, generate_password_hash(clave), es_admin)
            db.confirmar()
            _entrar(datos.usuario_por_id(usuario_id))
            flash(f"¡Bienvenido/a a SplitFácil, {nombre}!", "success")
            pendientes = datos.contar_invitaciones_pendientes(email)
            if seguridad.url_segura(destino):
                return redirect(destino)
            if pendientes:
                flash(f"Tienes {pendientes} invitación(es) esperándote.", "info")
                return redirect(url_for("invitaciones.bandeja"))
            return redirect(url_for("grupos.panel"))
        flash("Revisa los campos marcados en rojo.", "error")
    return render_template("auth/registro.html", valores=valores, errores=errores, destino=destino)


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    if g.user:
        return redirect(url_for("grupos.panel"))
    destino = request.values.get("next", "")
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        clave = request.form.get("clave", "")
        if seguridad.bloqueado(email):
            flash("Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.", "error")
        else:
            usuario = datos.usuario_por_email(email) if email else None
            hash_guardado = usuario["password_hash"] if usuario else _HASH_FALSO
            clave_ok = check_password_hash(hash_guardado, clave)
            if usuario and clave_ok:
                if not usuario["activo"]:
                    flash("Tu cuenta está desactivada. Escríbenos desde Contacto si crees que es un error.", "error")
                else:
                    seguridad.limpiar_fallos(email)
                    _entrar(usuario, recordar=bool(request.form.get("recordarme")))
                    flash(f"¡Hola de nuevo, {usuario['nombre']}!", "success")
                    return redirect(seguridad.url_segura(destino) or url_for("grupos.panel"))
            else:
                seguridad.registrar_fallo(email)
                flash("Correo o contraseña incorrectos.", "error")
    return render_template("auth/entrar.html", email=email, destino=destino)


@bp.post("/salir")
def salir():
    session.clear()
    flash("Cerraste sesión. ¡Hasta pronto!", "info")
    return redirect(url_for("principal.inicio"))


@bp.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        enlace_dev = None
        usuario = datos.usuario_por_email(email) if email_valido(email) else None
        if usuario and usuario["activo"]:
            enlace = url_for("auth.restablecer", token=seguridad.generar_token_recuperacion(usuario),
                             _external=True)
            if correo.configurado():
                try:
                    correo.enviar(email, "Recupera tu contraseña de SplitFácil",
                                  f"Hola {usuario['nombre']},\n\nPara crear una contraseña nueva entra aquí "
                                  f"(el enlace dura 1 hora):\n{enlace}\n\nSi no fuiste tú, ignora este mensaje.")
                except Exception:
                    current_app.logger.exception("No se pudo enviar el correo de recuperación")
            else:
                current_app.logger.warning("Enlace de recuperación para %s: %s", email, enlace)
                if current_app.config["MOSTRAR_ENLACES_RECUPERACION"]:
                    enlace_dev = enlace
        # Mismo mensaje exista o no el correo: así no se revela quién tiene cuenta.
        flash("Si ese correo está registrado, te enviamos las instrucciones para recuperar la contraseña.", "info")
        return render_template("auth/recuperar.html", enlace_dev=enlace_dev)
    return render_template("auth/recuperar.html", enlace_dev=None)


@bp.route("/restablecer/<token>", methods=["GET", "POST"])
def restablecer(token):
    usuario = seguridad.leer_token_recuperacion(token)
    if usuario is None:
        flash("El enlace no es válido o ya venció. Pide uno nuevo.", "error")
        return redirect(url_for("auth.recuperar"))
    errores = {}
    if request.method == "POST":
        clave = request.form.get("clave", "")
        clave2 = request.form.get("clave2", "")
        problema = clave_invalida(clave)
        if problema:
            errores["clave"] = problema
        elif clave != clave2:
            errores["clave2"] = "Las contraseñas no coinciden."
        if not errores:
            datos.actualizar_usuario(usuario["id"], password_hash=generate_password_hash(clave))
            db.confirmar()
            flash("Listo, cambiaste tu contraseña. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("auth.entrar"))
        flash("Revisa los campos marcados en rojo.", "error")
    return render_template("auth/restablecer.html", errores=errores, token=token)
