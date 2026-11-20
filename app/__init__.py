"""SplitFácil — fábrica de la aplicación (Tema 2: estructura profesional).

`create_app()` arma la aplicación pieza por pieza: configuración, base de datos,
seguridad, filtros de plantilla, blueprints (rutas), páginas de error y comandos.
Así se puede crear una app limpia para producción, desarrollo o pruebas.
"""
import os
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request
from werkzeug.security import generate_password_hash

from . import datos, db
from .config import BASE_DIR, obtener_config
from .seguridad import registrar_seguridad, token_csrf
from .utilidades import ACENTOS, CATEGORIAS, EMOJIS_GRUPO, EMOJIS_PERFIL, TEMAS, registrar_filtros

load_dotenv(BASE_DIR / ".env")  # lee las variables de entorno del archivo .env (si existe)


def create_app(nombre_config=None, ajustes=None):
    app = Flask(__name__)
    config = obtener_config(nombre_config or os.environ.get("APP_ENV", "development"))
    config.validar()
    app.config.from_object(config)
    if ajustes:
        app.config.update(ajustes)
    app.json.ensure_ascii = False  # que la API muestre tildes y ñ normales
    app.json.sort_keys = False
    if app.config.get("CONFIAR_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.teardown_appcontext(db.cerrar)
    registrar_seguridad(app)
    registrar_filtros(app)
    registrar_contexto(app)
    registrar_blueprints(app)
    registrar_errores(app)
    registrar_comandos(app)

    with app.app_context():
        if not db.es_postgres():
            Path(db._ruta_sqlite()).parent.mkdir(parents=True, exist_ok=True)
        db.crear_tablas()
        sembrar_admin(app)
    return app


def registrar_blueprints(app):
    from .routes import admin, api, auth, grupos, invitaciones, perfil, principal
    for modulo in (principal, auth, perfil, grupos, invitaciones, admin, api):
        app.register_blueprint(modulo.bp)


def registrar_contexto(app):
    """Variables disponibles en TODAS las plantillas."""
    app.jinja_env.globals["csrf_token"] = token_csrf  # también disponible dentro de las macros

    @app.context_processor
    def inyectar():
        usuario = g.get("user")
        if usuario:
            tema, acento = usuario["tema"], usuario["acento"]
        else:
            tema, acento = request.cookies.get("tema", "auto"), request.cookies.get("acento", "verde")
        if tema not in dict(TEMAS):
            tema = "auto"
        if acento not in dict(ACENTOS):
            acento = "verde"
        try:
            pendientes = datos.contar_invitaciones_pendientes(usuario["email"]) if usuario else 0
        except Exception:  # si la base falla, la página de error igual debe poder mostrarse
            pendientes = 0
        return {"tema": tema, "acento": acento, "csrf_token": token_csrf, "n_invitaciones": pendientes,
                "CATEGORIAS": CATEGORIAS, "EMOJIS_GRUPO": EMOJIS_GRUPO, "EMOJIS_PERFIL": EMOJIS_PERFIL,
                "TEMAS": TEMAS, "ACENTOS": ACENTOS}


def registrar_errores(app):
    mensajes = {
        400: ("Solicitud no válida", "No pudimos procesar el formulario. Recarga la página e inténtalo de nuevo."),
        403: ("Acceso denegado", "No tienes permiso para ver esta página."),
        404: ("No encontramos esa página", "Puede que el enlace esté mal escrito o que ya no exista."),
        405: ("Acción no permitida", "Esa dirección no acepta este tipo de solicitud."),
        413: ("Archivo demasiado grande", "Lo que enviaste pesa más de lo permitido."),
        500: ("Algo salió mal", "Tuvimos un problema de nuestro lado. Inténtalo de nuevo en un momento."),
    }

    def manejar(error):
        codigo = getattr(error, "code", 500) or 500
        if codigo >= 500:
            try:
                db.conexion().rollback()
            except Exception:
                pass
            app.logger.exception("Error interno: %s", error)
        titulo, texto = mensajes.get(codigo, ("Error", "Ocurrió un error inesperado."))
        if request.path.startswith("/api/"):
            return jsonify({"error": titulo, "detalle": texto}), codigo
        return render_template("errores/error.html", codigo=codigo, titulo=titulo, mensaje=texto), codigo

    for codigo in mensajes:
        app.register_error_handler(codigo, manejar)


def sembrar_admin(app):
    """Crea el administrador inicial a partir de ADMIN_EMAIL y ADMIN_PASSWORD (variables de entorno)."""
    email, clave = app.config["ADMIN_EMAIL"], app.config["ADMIN_PASSWORD"]
    if not email or not clave:
        return
    existente = datos.usuario_por_email(email)
    if existente is None:
        datos.crear_usuario(app.config["ADMIN_NOMBRE"], email, generate_password_hash(clave), es_admin=1)
        db.confirmar()
        app.logger.info("Administrador creado: %s", email)
    elif not existente["es_admin"]:
        datos.actualizar_usuario(existente["id"], es_admin=1)
        db.confirmar()


def registrar_comandos(app):
    from . import servicios

    @app.cli.command("crear-admin")
    @click.argument("email")
    @click.option("--nombre", default="Administrador", help="Nombre del administrador")
    @click.password_option(help="Contraseña (mínimo 8 caracteres, con letras y números)")
    def crear_admin(email, nombre, password):
        """Crea (o promueve) un administrador. Ej: flask --app run crear-admin yo@correo.com"""
        from .utilidades import clave_invalida, email_valido
        email = email.strip().lower()
        if not email_valido(email):
            raise click.ClickException("El correo no es válido.")
        problema = clave_invalida(password)
        if problema:
            raise click.ClickException(problema)
        existente = datos.usuario_por_email(email)
        if existente:
            datos.actualizar_usuario(existente["id"], es_admin=1)
        else:
            datos.crear_usuario(nombre, email, generate_password_hash(password), es_admin=1)
        db.confirmar()
        click.echo(f"Listo: {email} es administrador.")

    @app.cli.command("datos-demo")
    @click.argument("email")
    def datos_demo(email):
        """Carga los grupos de ejemplo en la cuenta de EMAIL."""
        usuario = datos.usuario_por_email(email)
        if not usuario:
            raise click.ClickException("No existe un usuario con ese correo.")
        servicios.crear_datos_demo(usuario)
        click.echo("Datos de ejemplo cargados.")

    @app.cli.command("reiniciar-bd")
    @click.confirmation_option(prompt="Esto BORRA todos los datos. ¿Continuar?")
    def reiniciar_bd():
        """Borra todas las tablas y las vuelve a crear (solo en desarrollo)."""
        if not (app.config["DEBUG"] or app.config["TESTING"]):
            raise click.ClickException("Por seguridad, este comando solo funciona en desarrollo.")
        for tabla in ("mensajes", "comentarios", "actividad", "invitaciones", "pagos", "participaciones",
                      "gastos", "miembros", "grupos", "usuarios"):
            db.conexion().execute(f"DROP TABLE IF EXISTS {tabla}")
        db.confirmar()
        db.crear_tablas()
        sembrar_admin(app)
        click.echo("Base de datos reiniciada.")
