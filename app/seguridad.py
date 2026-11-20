"""Seguridad (Tema 5): sesiones, autenticación, autorización, CSRF y cabeceras.

Autenticación  = ¿quién eres?        -> login_required
Autorización   = ¿qué puedes hacer?  -> admin_required y las comprobaciones de grupo
"""
import hmac
import secrets
import time
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, flash, g, redirect, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import datos

_FALLOS = {}  # {"ip|correo": [momentos de cada intento fallido]}


# ---------------------------------------------------------------------------
# Sesión: quién está usando la app en esta petición
# ---------------------------------------------------------------------------
def cargar_usuario():
    g.user = None
    if request.endpoint == "static":
        return
    usuario_id = session.get("usuario_id")
    if usuario_id is not None:
        usuario = datos.usuario_por_id(usuario_id)
        if usuario and usuario["activo"]:
            g.user = usuario
        else:
            session.pop("usuario_id", None)


def iniciar_sesion(usuario, recordar=False):
    session.clear()  # evita que alguien "reutilice" una sesión anterior
    session["usuario_id"] = usuario["id"]
    session.permanent = bool(recordar)


# ---------------------------------------------------------------------------
# Decoradores de acceso
# ---------------------------------------------------------------------------
def login_required(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if g.user is None:
            flash("Inicia sesión para continuar.", "warning")
            destino = request.full_path.rstrip("?") if request.method == "GET" else None
            return redirect(url_for("auth.entrar", next=destino))
        return vista(*args, **kwargs)
    return envoltura


def admin_required(vista):
    @wraps(vista)
    @login_required
    def envoltura(*args, **kwargs):
        if not g.user["es_admin"]:
            abort(403)  # logueado, pero sin permiso
        return vista(*args, **kwargs)
    return envoltura


# ---------------------------------------------------------------------------
# CSRF: evita que otra página envíe formularios en tu nombre
# ---------------------------------------------------------------------------
def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def verificar_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if request.blueprint == "api" and request.headers.get("Authorization", "").startswith("Bearer "):
        return  # la API con token no usa cookies, así que no necesita CSRF
    enviado = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    esperado = session.get("csrf", "")
    if not esperado or not hmac.compare_digest(enviado, esperado):
        abort(400)


# ---------------------------------------------------------------------------
# Redirecciones seguras (evita "open redirect")
# ---------------------------------------------------------------------------
def url_segura(destino):
    """Solo acepta rutas internas como /panel. Devuelve None si el destino es sospechoso."""
    if not destino or not destino.startswith("/") or destino.startswith("//") or "\\" in destino:
        return None
    partes = urlparse(destino)
    return destino if not partes.netloc and not partes.scheme else None


def volver_a(por_defecto):
    referencia = urlparse(request.referrer or "")
    if referencia.netloc == request.host and referencia.path:
        return referencia.path + (f"?{referencia.query}" if referencia.query else "")
    return por_defecto


# ---------------------------------------------------------------------------
# Límite de intentos de inicio de sesión
# ---------------------------------------------------------------------------
def _clave(correo):
    return f"{request.remote_addr}|{correo.lower()}"


def bloqueado(correo):
    ventana = current_app.config["LOGIN_VENTANA_SEG"]
    ahora = time.time()
    recientes = [t for t in _FALLOS.get(_clave(correo), []) if ahora - t < ventana]
    _FALLOS[_clave(correo)] = recientes
    return len(recientes) >= current_app.config["LOGIN_MAX_INTENTOS"]


def registrar_fallo(correo):
    _FALLOS.setdefault(_clave(correo), []).append(time.time())


def limpiar_fallos(correo):
    _FALLOS.pop(_clave(correo), None)


# ---------------------------------------------------------------------------
# Recuperar contraseña: enlace firmado que caduca en 1 hora y sirve una sola vez
# ---------------------------------------------------------------------------
def _serializador():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="recuperar-clave")


def generar_token_recuperacion(usuario):
    # Incluimos un pedazo de la clave actual: al cambiarla, el enlace viejo deja de servir.
    return _serializador().dumps({"u": usuario["id"], "h": usuario["password_hash"][-12:]})


def leer_token_recuperacion(token, max_edad=3600):
    try:
        carga = _serializador().loads(token, max_age=max_edad)
    except BadSignature:  # también cubre la firma caducada
        return None
    usuario = datos.usuario_por_id(carga.get("u"))
    if usuario and usuario["activo"] and usuario["password_hash"][-12:] == carga.get("h"):
        return usuario
    return None


# ---------------------------------------------------------------------------
# Cabeceras de seguridad en todas las respuestas
# ---------------------------------------------------------------------------
def cabeceras_seguras(respuesta):
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "same-origin")
    respuesta.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if current_app.config.get("SESSION_COOKIE_SECURE"):
        respuesta.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.endpoint != "static" and g.get("user"):
        respuesta.headers.setdefault("Cache-Control", "no-store")  # no guardar páginas privadas en caché
    return respuesta


def registrar_seguridad(app):
    app.before_request(cargar_usuario)
    app.before_request(verificar_csrf)
    app.after_request(cabeceras_seguras)
