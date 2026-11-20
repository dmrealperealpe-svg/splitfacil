"""Conexión a la base de datos y creación de tablas (Tema 3).

Usamos SQL directo, así se ve exactamente qué pasa en cada operación.
Funciona con SQLite (archivo local, no requiere instalar nada) y, opcionalmente,
con PostgreSQL/Supabase si defines DATABASE_URL y instalas `psycopg`.

Todas las consultas del proyecto usan `?` como marcador de parámetros; aquí se
adaptan solas al motor. NUNCA se arma una consulta pegando texto del usuario:
los valores siempre viajan como parámetros (así se evita la inyección SQL).
"""
import sqlite3
from urllib.parse import unquote, urlparse

from flask import current_app, g

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id {PK},
    nombre TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    es_admin INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1,
    bio TEXT NOT NULL DEFAULT '',
    emoji TEXT NOT NULL DEFAULT '',
    tema TEXT NOT NULL DEFAULT 'auto',
    acento TEXT NOT NULL DEFAULT 'verde',
    token_api_hash TEXT UNIQUE,
    creado_en TEXT NOT NULL,
    ultimo_acceso TEXT
);
CREATE TABLE IF NOT EXISTS grupos (
    id {PK},
    nombre TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '',
    emoji TEXT NOT NULL DEFAULT '🏠',
    creado_por_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS miembros (
    id {PK},
    grupo_id INTEGER NOT NULL REFERENCES grupos(id) ON DELETE CASCADE,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nombre_invitado TEXT,
    es_propietario INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT NOT NULL,
    UNIQUE (grupo_id, usuario_id)
);
CREATE TABLE IF NOT EXISTS gastos (
    id {PK},
    grupo_id INTEGER NOT NULL REFERENCES grupos(id) ON DELETE CASCADE,
    descripcion TEXT NOT NULL,
    monto INTEGER NOT NULL CHECK (monto > 0),
    categoria TEXT NOT NULL DEFAULT 'otros',
    fecha TEXT NOT NULL,
    pagado_por_id INTEGER NOT NULL REFERENCES miembros(id) ON DELETE CASCADE,
    creado_por_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    tipo_division TEXT NOT NULL DEFAULT 'igual',
    nota TEXT NOT NULL DEFAULT '',
    creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS participaciones (
    id {PK},
    gasto_id INTEGER NOT NULL REFERENCES gastos(id) ON DELETE CASCADE,
    miembro_id INTEGER NOT NULL REFERENCES miembros(id) ON DELETE CASCADE,
    monto INTEGER NOT NULL CHECK (monto >= 0)
);
CREATE TABLE IF NOT EXISTS pagos (
    id {PK},
    grupo_id INTEGER NOT NULL REFERENCES grupos(id) ON DELETE CASCADE,
    de_miembro_id INTEGER NOT NULL REFERENCES miembros(id) ON DELETE CASCADE,
    a_miembro_id INTEGER NOT NULL REFERENCES miembros(id) ON DELETE CASCADE,
    monto INTEGER NOT NULL CHECK (monto > 0),
    fecha TEXT NOT NULL,
    nota TEXT NOT NULL DEFAULT '',
    creado_por_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    creado_en TEXT NOT NULL,
    CHECK (de_miembro_id <> a_miembro_id)
);
CREATE TABLE IF NOT EXISTS invitaciones (
    id {PK},
    grupo_id INTEGER NOT NULL REFERENCES grupos(id) ON DELETE CASCADE,
    invitado_por_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    email TEXT,
    miembro_id INTEGER REFERENCES miembros(id) ON DELETE SET NULL,
    token TEXT NOT NULL UNIQUE,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    creado_en TEXT NOT NULL,
    respondido_en TEXT
);
CREATE TABLE IF NOT EXISTS actividad (
    id {PK},
    grupo_id INTEGER NOT NULL REFERENCES grupos(id) ON DELETE CASCADE,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    texto TEXT NOT NULL,
    creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comentarios (
    id {PK},
    grupo_id INTEGER NOT NULL REFERENCES grupos(id) ON DELETE CASCADE,
    gasto_id INTEGER REFERENCES gastos(id) ON DELETE CASCADE,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    texto TEXT NOT NULL,
    creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mensajes (
    id {PK},
    nombre TEXT NOT NULL,
    email TEXT NOT NULL,
    texto TEXT NOT NULL,
    leido INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_miembros_grupo ON miembros(grupo_id);
CREATE INDEX IF NOT EXISTS idx_miembros_usuario ON miembros(usuario_id);
CREATE INDEX IF NOT EXISTS idx_gastos_grupo ON gastos(grupo_id);
CREATE INDEX IF NOT EXISTS idx_participaciones_gasto ON participaciones(gasto_id);
CREATE INDEX IF NOT EXISTS idx_pagos_grupo ON pagos(grupo_id);
CREATE INDEX IF NOT EXISTS idx_invitaciones_email ON invitaciones(email);
CREATE INDEX IF NOT EXISTS idx_actividad_grupo ON actividad(grupo_id);
CREATE INDEX IF NOT EXISTS idx_comentarios_grupo ON comentarios(grupo_id);
CREATE INDEX IF NOT EXISTS idx_comentarios_gasto ON comentarios(gasto_id)
"""


def es_postgres():
    return current_app.config["DATABASE_URL"].startswith("postgresql://")


def _ruta_sqlite():
    url = current_app.config["DATABASE_URL"]
    ruta = unquote(urlparse(url).path) if not url.startswith("sqlite:///") else url[len("sqlite:///"):]
    return ruta


def conexion():
    """Una conexión por petición, guardada en `g` y cerrada al terminar."""
    if "db" not in g:
        if es_postgres():
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as error:  # pragma: no cover
                raise RuntimeError(
                    "Para usar PostgreSQL instala el paquete: pip install \"psycopg[binary]\""
                ) from error
            g.db = psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row)
        else:
            conn = sqlite3.connect(_ruta_sqlite())
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")  # sin esto SQLite ignora las llaves foráneas
            g.db = conn
    return g.db


def _adaptar(sql):
    return sql.replace("?", "%s") if es_postgres() else sql


def _como_dict(fila):
    return None if fila is None else dict(fila)


def consultar(sql, params=()):
    """SELECT que devuelve una lista de diccionarios."""
    cursor = conexion().execute(_adaptar(sql), tuple(params))
    return [dict(f) for f in cursor.fetchall()]


def uno(sql, params=()):
    """SELECT que devuelve una sola fila (o None)."""
    cursor = conexion().execute(_adaptar(sql), tuple(params))
    return _como_dict(cursor.fetchone())


def valor(sql, params=(), defecto=None):
    """SELECT que devuelve un solo dato (por ejemplo un COUNT)."""
    fila = uno(sql, params)
    if not fila:
        return defecto
    dato = next(iter(fila.values()))
    return defecto if dato is None else dato


def ejecutar(sql, params=()):
    """UPDATE / DELETE. Devuelve cuántas filas cambió."""
    return conexion().execute(_adaptar(sql), tuple(params)).rowcount


def insertar(sql, params=()):
    """INSERT. Devuelve el id de la fila nueva."""
    conn = conexion()
    if es_postgres():
        return conn.execute(_adaptar(sql) + " RETURNING id", tuple(params)).fetchone()["id"]
    return conn.execute(sql, tuple(params)).lastrowid


def confirmar():
    conexion().commit()


def cerrar(_error=None):
    conn = g.pop("db", None)
    if conn is not None:
        try:
            conn.rollback()  # si algo falló antes de confirmar, no queda nada a medias
        finally:
            conn.close()


def crear_tablas():
    pk = "SERIAL PRIMARY KEY" if es_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    for sentencia in ESQUEMA.replace("{PK}", pk).split(";"):
        if sentencia.strip():
            conexion().execute(sentencia)
    confirmar()
