"""Configuración de SplitFácil.

Tema 5 y 7: los secretos y las opciones que cambian entre tu computador y el
servidor NO se escriben en el código: se leen de variables de entorno
(archivo .env en desarrollo, panel del servidor en producción).
"""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CLAVE_DESARROLLO = "clave-solo-para-desarrollo-no-usar-en-produccion"


def _texto(nombre, defecto=""):
    return os.environ.get(nombre, defecto).strip()


def _booleano(nombre, defecto=False):
    valor = os.environ.get(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes", "on")


def _entero(nombre, defecto):
    try:
        return int(os.environ.get(nombre, defecto))
    except (TypeError, ValueError):
        return defecto


def _url_base_de_datos():
    """DATABASE_URL vacía = SQLite local. postgresql://... = PostgreSQL (Supabase)."""
    url = _texto("DATABASE_URL")
    if not url:
        return "sqlite:///" + (BASE_DIR / "instance" / "splitfacil.db").as_posix()
    if url.startswith("postgres://"):  # algunos servidores usan este prefijo antiguo
        url = "postgresql://" + url[len("postgres://"):]
    return url


class Config:
    """Valores comunes a todos los entornos."""

    def __init__(self):
        self.SECRET_KEY = _texto("SECRET_KEY") or CLAVE_DESARROLLO
        self.DATABASE_URL = _url_base_de_datos()

        # Cookies de sesión
        self.SESSION_COOKIE_HTTPONLY = True
        self.SESSION_COOKIE_SAMESITE = "Lax"
        self.SESSION_COOKIE_SECURE = False
        self.PERMANENT_SESSION_LIFETIME = timedelta(days=14)
        self.MAX_CONTENT_LENGTH = 512 * 1024  # 512 KB por petición

        # Administrador inicial (se crea al arrancar si no existe)
        self.ADMIN_EMAIL = _texto("ADMIN_EMAIL").lower()
        self.ADMIN_PASSWORD = _texto("ADMIN_PASSWORD")
        self.ADMIN_NOMBRE = _texto("ADMIN_NOMBRE", "Administrador")

        # Intentos de inicio de sesión
        self.LOGIN_MAX_INTENTOS = _entero("LOGIN_MAX_INTENTOS", 5)
        self.LOGIN_VENTANA_SEG = _entero("LOGIN_VENTANA_SEG", 600)

        # Zona horaria fija (Colombia = UTC-5, sin horario de verano)
        self.ZONA_HORARIA_HORAS = _entero("ZONA_HORARIA_HORAS", -5)

        # Correo para recuperar contraseñas (opcional)
        self.MAIL_SERVER = _texto("MAIL_SERVER")
        self.MAIL_PORT = _entero("MAIL_PORT", 587)
        self.MAIL_USER = _texto("MAIL_USER")
        self.MAIL_PASSWORD = _texto("MAIL_PASSWORD")
        self.MAIL_FROM = _texto("MAIL_FROM") or self.MAIL_USER
        self.MOSTRAR_ENLACES_RECUPERACION = False

        # Detrás de un servidor con HTTPS (Render, Railway...) hay un "proxy" delante de la app.
        # Con esto Flask lee bien la IP real y el https de cada visita.
        self.CONFIAR_PROXY = _booleano("CONFIAR_PROXY", False)

        self.DEBUG = False
        self.TESTING = False

    def validar(self):
        """Se llama al arrancar; las subclases pueden rechazar configuraciones peligrosas."""


class DesarrolloConfig(Config):
    def __init__(self):
        super().__init__()
        self.DEBUG = True
        # Sin servidor de correo, mostramos el enlace de recuperación en pantalla.
        self.MOSTRAR_ENLACES_RECUPERACION = True


class ProduccionConfig(Config):
    def __init__(self):
        super().__init__()
        # Detrás de HTTPS la cookie debe viajar solo cifrada.
        self.SESSION_COOKIE_SECURE = _booleano("COOKIE_SEGURA", True)
        self.CONFIAR_PROXY = _booleano("CONFIAR_PROXY", True)

    def validar(self):
        if self.SECRET_KEY == CLAVE_DESARROLLO or len(self.SECRET_KEY) < 24:
            raise RuntimeError(
                "En producción debes definir SECRET_KEY (mínimo 24 caracteres) "
                "como variable de entorno. Genera una con: "
                "python -c \"import secrets; print(secrets.token_hex(32))\""
            )


class PruebasConfig(Config):
    def __init__(self):
        super().__init__()
        self.TESTING = True
        self.SECRET_KEY = "clave-de-pruebas"
        self.ADMIN_EMAIL = ""
        self.ADMIN_PASSWORD = ""


def obtener_config(nombre):
    clases = {
        "development": DesarrolloConfig,
        "production": ProduccionConfig,
        "testing": PruebasConfig,
    }
    if nombre not in clases:
        raise ValueError(f"APP_ENV desconocido: {nombre!r}. Usa development, production o testing.")
    return clases[nombre]()
