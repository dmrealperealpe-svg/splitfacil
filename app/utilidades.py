"""Funciones auxiliares: dinero, fechas, validaciones y catálogos."""
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

from flask import current_app

# ---------------------------------------------------------------------------
# Catálogos (las opciones que aparecen en listas y selectores)
# ---------------------------------------------------------------------------
CATEGORIAS = {
    "comida": ("Comida", "🍽️"),
    "transporte": ("Transporte", "🚗"),
    "hogar": ("Hogar", "🏠"),
    "servicios": ("Servicios", "💡"),
    "ocio": ("Ocio", "🎉"),
    "viajes": ("Viajes", "✈️"),
    "compras": ("Compras", "🛒"),
    "salud": ("Salud", "💊"),
    "otros": ("Otros", "📦"),
}
EMOJIS_GRUPO = ["🏠", "✈️", "🍽️", "🎉", "🚗", "🏖️", "🛒", "💼", "🎓", "⚽", "🎬", "❤️"]
EMOJIS_PERFIL = ["🙂", "😎", "🤓", "🦊", "🐼", "🐯", "🦄", "🌻", "🚀", "🎧", "☕", "🌈"]
TEMAS = [("auto", "Automático"), ("claro", "Claro"), ("oscuro", "Oscuro")]
ACENTOS = [("verde", "Verde"), ("azul", "Azul"), ("violeta", "Violeta"),
           ("naranja", "Naranja"), ("rosa", "Rosa")]

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


# ---------------------------------------------------------------------------
# Tiempo. En la base de datos todo se guarda en UTC como texto ISO.
# ---------------------------------------------------------------------------
def ahora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _zona():
    return timezone(timedelta(hours=current_app.config.get("ZONA_HORARIA_HORAS", -5)))


def hoy_local():
    return datetime.now(_zona()).strftime("%Y-%m-%d")


def _a_datetime(valor):
    """Convierte texto/date/datetime en un datetime con zona horaria local."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        dt = valor
    elif isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day, tzinfo=_zona())
    else:
        texto = str(valor)
        try:
            dt = datetime.strptime(texto[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                d = datetime.strptime(texto[:10], "%Y-%m-%d")
            except ValueError:
                return None
            return d.replace(tzinfo=_zona())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_zona())


def cop(monto):
    """1200000 -> $1.200.000 (pesos colombianos)."""
    try:
        n = round(float(monto))
    except (TypeError, ValueError):
        return "$0"
    signo = "-" if n < 0 else ""
    return f"{signo}${abs(n):,}".replace(",", ".")


def fecha(valor):
    dt = _a_datetime(valor)
    return "" if dt is None else f"{dt.day} {MESES[dt.month - 1]} {dt.year}"


def fecha_hora(valor):
    dt = _a_datetime(valor)
    if dt is None:
        return ""
    return f"{dt.day} {MESES[dt.month - 1]} {dt.year}, {dt:%H:%M}"


def hace(valor):
    """Tiempo relativo: 'hace 5 min', 'hace 2 h', 'hace 3 días'."""
    dt = _a_datetime(valor)
    if dt is None:
        return ""
    segundos = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
    if segundos < 60:
        return "hace un momento"
    if segundos < 3600:
        return f"hace {int(segundos // 60)} min"
    if segundos < 86400:
        return f"hace {int(segundos // 3600)} h"
    if segundos < 7 * 86400:
        dias = int(segundos // 86400)
        return "ayer" if dias == 1 else f"hace {dias} días"
    return fecha(valor)


def iniciales(nombre):
    partes = (nombre or "?").split()
    return "".join(p[0] for p in partes[:2]).upper() or "?"


def tono_avatar(nombre):
    """Un color estable para cada nombre (0-359)."""
    return sum(ord(c) * (i + 1) for i, c in enumerate(nombre or "?")) % 360


def slug(texto):
    normal = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normal.lower()).strip("-") or "grupo"


# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------
def parse_monto(texto, minimo=1, maximo=1_000_000_000):
    """Acepta '35000', '35.000' o '$35,000'. Devuelve un entero o None si no es válido."""
    limpio = re.sub(r"[\s$.,]", "", str(texto if texto is not None else ""))
    if not limpio:
        return 0 if minimo == 0 else None
    if not (limpio.isascii() and limpio.isdigit()):
        return None
    valor = int(limpio)
    if valor < minimo or valor > maximo:
        return None
    return valor


def email_valido(email):
    return bool(EMAIL_RE.match(email or "")) and len(email) <= 120


def clave_invalida(clave):
    """Devuelve el mensaje de error si la contraseña es débil, o None si está bien."""
    if len(clave) < 8:
        return "La contraseña debe tener mínimo 8 caracteres."
    if not re.search(r"[A-Za-z]", clave) or not re.search(r"\d", clave):
        return "Usa letras y números en tu contraseña."
    if len(clave) > 128:
        return "La contraseña es demasiado larga."
    return None


def escapar_like(texto):
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def seguro_csv(texto):
    """Evita que Excel ejecute fórmulas escritas por usuarios (inyección CSV)."""
    texto = str(texto)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@") else texto


def registrar_filtros(app):
    app.add_template_filter(cop, "cop")
    app.add_template_filter(fecha, "fecha")
    app.add_template_filter(fecha_hora, "fecha_hora")
    app.add_template_filter(hace, "hace")
    app.add_template_filter(iniciales, "iniciales")
    app.add_template_filter(tono_avatar, "tono")
