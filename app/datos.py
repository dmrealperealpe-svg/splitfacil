"""Consultas SQL de SplitFácil (Tema 3: CRUD).

Aquí vive TODO el SQL del proyecto. Las rutas y la lógica llaman a estas
funciones y no escriben SQL por su cuenta. Cada función hace una cosa:

    Crear (INSERT) · Leer (SELECT) · Actualizar (UPDATE) · Eliminar (DELETE)

Las filas se devuelven como diccionarios: fila["nombre"].
"""
from . import db
from .utilidades import ahora, escapar_like

LIKE = " LIKE ? ESCAPE '\\'"


def _marcadores(n):
    return ",".join("?" * n)


def _actualizar(tabla, permitidas, id_, campos):
    """UPDATE seguro: solo acepta columnas de la lista blanca `permitidas`."""
    invalidas = set(campos) - set(permitidas)
    if invalidas or not campos:
        raise ValueError(f"Columnas no permitidas en {tabla}: {invalidas or 'ninguna'}")
    asignaciones = ", ".join(f"{col} = ?" for col in campos)
    return db.ejecutar(f"UPDATE {tabla} SET {asignaciones} WHERE id = ?", [*campos.values(), id_])


# ===========================================================================
# USUARIOS
# ===========================================================================
COLUMNAS_USUARIO = ("nombre", "bio", "emoji", "tema", "acento", "password_hash",
                    "token_api_hash", "es_admin", "activo", "ultimo_acceso")


def crear_usuario(nombre, email, password_hash, es_admin=0):
    return db.insertar(
        "INSERT INTO usuarios (nombre, email, password_hash, es_admin, creado_en) VALUES (?, ?, ?, ?, ?)",
        [nombre, email, password_hash, 1 if es_admin else 0, ahora()],
    )


def usuario_por_id(usuario_id):
    return db.uno("SELECT * FROM usuarios WHERE id = ?", [usuario_id])


def usuario_por_email(email):
    return db.uno("SELECT * FROM usuarios WHERE email = ?", [email.strip().lower()])


def usuario_por_token(token_hash):
    return db.uno("SELECT * FROM usuarios WHERE token_api_hash = ? AND activo = 1", [token_hash])


def actualizar_usuario(usuario_id, **campos):
    return _actualizar("usuarios", COLUMNAS_USUARIO, usuario_id, campos)


def borrar_usuario(usuario_id):
    return db.ejecutar("DELETE FROM usuarios WHERE id = ?", [usuario_id])


def buscar_usuarios(texto="", limite=15, desplazamiento=0):
    donde, params = "", []
    if texto:
        donde = f" WHERE (LOWER(u.nombre){LIKE} OR LOWER(u.email){LIKE})"
        patron = f"%{escapar_like(texto.lower())}%"
        params = [patron, patron]
    return db.consultar(
        "SELECT u.id, u.nombre, u.email, u.es_admin, u.activo, u.creado_en, u.ultimo_acceso, "
        "(SELECT COUNT(*) FROM miembros m WHERE m.usuario_id = u.id) AS n_grupos "
        f"FROM usuarios u{donde} ORDER BY u.id DESC LIMIT ? OFFSET ?",
        [*params, limite, desplazamiento],
    )


def contar_usuarios(texto=""):
    if not texto:
        return db.valor("SELECT COUNT(*) FROM usuarios", defecto=0)
    patron = f"%{escapar_like(texto.lower())}%"
    return db.valor(
        f"SELECT COUNT(*) FROM usuarios u WHERE (LOWER(u.nombre){LIKE} OR LOWER(u.email){LIKE})",
        [patron, patron], defecto=0)


def contar_admins():
    return db.valor("SELECT COUNT(*) FROM usuarios WHERE es_admin = 1 AND activo = 1", defecto=0)


# ===========================================================================
# GRUPOS
# ===========================================================================
def crear_grupo(nombre, descripcion, emoji, creado_por_id):
    return db.insertar(
        "INSERT INTO grupos (nombre, descripcion, emoji, creado_por_id, creado_en) VALUES (?, ?, ?, ?, ?)",
        [nombre, descripcion, emoji, creado_por_id, ahora()],
    )


def grupo_por_id(grupo_id):
    return db.uno("SELECT * FROM grupos WHERE id = ?", [grupo_id])


def grupos_de_usuario(usuario_id):
    return db.consultar(
        "SELECT gr.*, m.id AS mi_miembro_id, m.es_propietario AS soy_propietario, "
        "(SELECT COUNT(*) FROM miembros x WHERE x.grupo_id = gr.id) AS n_miembros, "
        "(SELECT COUNT(*) FROM gastos y WHERE y.grupo_id = gr.id) AS n_gastos "
        "FROM grupos gr JOIN miembros m ON m.grupo_id = gr.id "
        "WHERE m.usuario_id = ? ORDER BY gr.id DESC",
        [usuario_id],
    )


def actualizar_grupo(grupo_id, nombre, descripcion, emoji):
    return db.ejecutar("UPDATE grupos SET nombre = ?, descripcion = ?, emoji = ? WHERE id = ?",
                       [nombre, descripcion, emoji, grupo_id])


def borrar_grupo(grupo_id):
    # Los miembros, gastos, pagos, invitaciones y actividad se borran solos (ON DELETE CASCADE).
    return db.ejecutar("DELETE FROM grupos WHERE id = ?", [grupo_id])


def buscar_grupos(texto="", limite=15, desplazamiento=0):
    donde, params = "", []
    if texto:
        donde = f" WHERE LOWER(gr.nombre){LIKE}"
        params = [f"%{escapar_like(texto.lower())}%"]
    return db.consultar(
        "SELECT gr.id, gr.nombre, gr.emoji, gr.creado_en, u.nombre AS creador, "
        "(SELECT COUNT(*) FROM miembros x WHERE x.grupo_id = gr.id) AS n_miembros, "
        "(SELECT COUNT(*) FROM gastos y WHERE y.grupo_id = gr.id) AS n_gastos, "
        "(SELECT COALESCE(SUM(z.monto), 0) FROM gastos z WHERE z.grupo_id = gr.id) AS total "
        f"FROM grupos gr LEFT JOIN usuarios u ON u.id = gr.creado_por_id{donde} "
        "ORDER BY gr.id DESC LIMIT ? OFFSET ?",
        [*params, limite, desplazamiento],
    )


def contar_grupos(texto=""):
    if not texto:
        return db.valor("SELECT COUNT(*) FROM grupos", defecto=0)
    return db.valor(f"SELECT COUNT(*) FROM grupos gr WHERE LOWER(gr.nombre){LIKE}",
                    [f"%{escapar_like(texto.lower())}%"], defecto=0)


# ===========================================================================
# MIEMBROS (personas de un grupo: con cuenta o invitados sin cuenta)
# ===========================================================================
SELECT_MIEMBRO = (
    "SELECT m.id, m.grupo_id, m.usuario_id, m.es_propietario, "
    "COALESCE(u.nombre, m.nombre_invitado, 'Alguien') AS nombre, "
    "COALESCE(u.emoji, '') AS emoji, u.email AS email "
    "FROM miembros m LEFT JOIN usuarios u ON u.id = m.usuario_id "
)


def _miembro(fila):
    if fila:
        fila["tiene_cuenta"] = fila["usuario_id"] is not None
    return fila


def miembros_de_grupo(grupo_id):
    filas = db.consultar(SELECT_MIEMBRO + "WHERE m.grupo_id = ? ORDER BY m.id", [grupo_id])
    return [_miembro(f) for f in filas]


def miembro_por_id(miembro_id):
    return _miembro(db.uno(SELECT_MIEMBRO + "WHERE m.id = ?", [miembro_id]))


def miembro_de_usuario(grupo_id, usuario_id):
    return _miembro(db.uno(SELECT_MIEMBRO + "WHERE m.grupo_id = ? AND m.usuario_id = ?",
                           [grupo_id, usuario_id]))


def membresias_de_usuario(usuario_id):
    return db.consultar("SELECT id, grupo_id, es_propietario FROM miembros WHERE usuario_id = ?",
                        [usuario_id])


def crear_miembro(grupo_id, usuario_id=None, nombre_invitado=None, es_propietario=0):
    return db.insertar(
        "INSERT INTO miembros (grupo_id, usuario_id, nombre_invitado, es_propietario, creado_en) "
        "VALUES (?, ?, ?, ?, ?)",
        [grupo_id, usuario_id, nombre_invitado, 1 if es_propietario else 0, ahora()],
    )


def actualizar_miembro(miembro_id, **campos):
    return _actualizar("miembros", ("usuario_id", "nombre_invitado", "es_propietario"), miembro_id, campos)


def borrar_miembro(miembro_id):
    return db.ejecutar("DELETE FROM miembros WHERE id = ?", [miembro_id])


def miembro_tiene_movimientos(miembro_id):
    return db.valor(
        "SELECT (SELECT COUNT(*) FROM gastos WHERE pagado_por_id = ?) + "
        "(SELECT COUNT(*) FROM participaciones WHERE miembro_id = ?) + "
        "(SELECT COUNT(*) FROM pagos WHERE de_miembro_id = ? OR a_miembro_id = ?)",
        [miembro_id] * 4, defecto=0) > 0


# ===========================================================================
# GASTOS
# ===========================================================================
def crear_gasto(grupo_id, descripcion, monto, categoria, fecha, pagado_por_id,
                creado_por_id, tipo_division, nota):
    return db.insertar(
        "INSERT INTO gastos (grupo_id, descripcion, monto, categoria, fecha, pagado_por_id, "
        "creado_por_id, tipo_division, nota, creado_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [grupo_id, descripcion, monto, categoria, fecha, pagado_por_id,
         creado_por_id, tipo_division, nota, ahora()],
    )


def actualizar_gasto(gasto_id, descripcion, monto, categoria, fecha, pagado_por_id, tipo_division, nota):
    return db.ejecutar(
        "UPDATE gastos SET descripcion = ?, monto = ?, categoria = ?, fecha = ?, pagado_por_id = ?, "
        "tipo_division = ?, nota = ? WHERE id = ?",
        [descripcion, monto, categoria, fecha, pagado_por_id, tipo_division, nota, gasto_id],
    )


def gasto_por_id(gasto_id):
    return db.uno("SELECT * FROM gastos WHERE id = ?", [gasto_id])


def borrar_gasto(gasto_id):
    return db.ejecutar("DELETE FROM gastos WHERE id = ?", [gasto_id])


def _filtro_gastos(grupo_id, texto, categoria):
    condiciones, params = ["ga.grupo_id = ?"], [grupo_id]
    if texto:
        condiciones.append(f"LOWER(ga.descripcion){LIKE}")
        params.append(f"%{escapar_like(texto.lower())}%")
    if categoria:
        condiciones.append("ga.categoria = ?")
        params.append(categoria)
    return " AND ".join(condiciones), params


def gastos_de_grupo(grupo_id, miembro_id, texto="", categoria="", limite=15, desplazamiento=0):
    """Gastos con el nombre de quien pagó y cuánto le toca pagar a `miembro_id`."""
    donde, params = _filtro_gastos(grupo_id, texto, categoria)
    return db.consultar(
        "SELECT ga.*, COALESCE(u.nombre, m.nombre_invitado, 'Alguien') AS pagador, "
        "(SELECT COALESCE(SUM(p.monto), 0) FROM participaciones p "
        " WHERE p.gasto_id = ga.id AND p.miembro_id = ?) AS mi_parte, "
        "(SELECT COUNT(*) FROM participaciones p2 WHERE p2.gasto_id = ga.id) AS n_participantes, "
        "(SELECT COUNT(*) FROM comentarios c WHERE c.gasto_id = ga.id) AS n_comentarios "
        "FROM gastos ga JOIN miembros m ON m.id = ga.pagado_por_id "
        "LEFT JOIN usuarios u ON u.id = m.usuario_id "
        f"WHERE {donde} ORDER BY ga.fecha DESC, ga.id DESC LIMIT ? OFFSET ?",
        [miembro_id, *params, limite, desplazamiento],
    )


def contar_gastos(grupo_id, texto="", categoria=""):
    donde, params = _filtro_gastos(grupo_id, texto, categoria)
    return db.valor(f"SELECT COUNT(*) FROM gastos ga WHERE {donde}", params, defecto=0)


def participaciones_de_gasto(gasto_id):
    filas = db.consultar("SELECT miembro_id, monto FROM participaciones WHERE gasto_id = ?", [gasto_id])
    return {f["miembro_id"]: f["monto"] for f in filas}


def reemplazar_participaciones(gasto_id, partes):
    """`partes` = {miembro_id: monto}. Borra las anteriores y guarda las nuevas."""
    db.ejecutar("DELETE FROM participaciones WHERE gasto_id = ?", [gasto_id])
    for miembro_id, monto in partes.items():
        db.insertar("INSERT INTO participaciones (gasto_id, miembro_id, monto) VALUES (?, ?, ?)",
                    [gasto_id, miembro_id, monto])


def gastos_para_exportar(grupo_id):
    gastos = db.consultar(
        "SELECT ga.id, ga.fecha, ga.descripcion, ga.categoria, ga.monto, ga.tipo_division, ga.nota, "
        "COALESCE(u.nombre, m.nombre_invitado, 'Alguien') AS pagador "
        "FROM gastos ga JOIN miembros m ON m.id = ga.pagado_por_id "
        "LEFT JOIN usuarios u ON u.id = m.usuario_id "
        "WHERE ga.grupo_id = ? ORDER BY ga.fecha, ga.id", [grupo_id])
    partes = db.consultar(
        "SELECT p.gasto_id, p.monto, COALESCE(u.nombre, m.nombre_invitado, 'Alguien') AS nombre "
        "FROM participaciones p JOIN gastos ga ON ga.id = p.gasto_id "
        "JOIN miembros m ON m.id = p.miembro_id LEFT JOIN usuarios u ON u.id = m.usuario_id "
        "WHERE ga.grupo_id = ? ORDER BY p.id", [grupo_id])
    por_gasto = {}
    for p in partes:
        por_gasto.setdefault(p["gasto_id"], []).append(p)
    for g_ in gastos:
        g_["partes"] = por_gasto.get(g_["id"], [])
    return gastos


def total_gastado(grupo_id):
    return int(db.valor("SELECT COALESCE(SUM(monto), 0) FROM gastos WHERE grupo_id = ?", [grupo_id], defecto=0))


def resumen_categorias(grupo_id):
    filas = db.consultar(
        "SELECT categoria, SUM(monto) AS total, COUNT(*) AS n FROM gastos "
        "WHERE grupo_id = ? GROUP BY categoria ORDER BY total DESC", [grupo_id])
    for f in filas:
        f["total"] = int(f["total"])
    return filas


# ===========================================================================
# PAGOS (cuando alguien le paga a otra persona para saldar deudas)
# ===========================================================================
def crear_pago(grupo_id, de_miembro_id, a_miembro_id, monto, fecha, nota, creado_por_id):
    return db.insertar(
        "INSERT INTO pagos (grupo_id, de_miembro_id, a_miembro_id, monto, fecha, nota, creado_por_id, creado_en) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [grupo_id, de_miembro_id, a_miembro_id, monto, fecha, nota, creado_por_id, ahora()],
    )


def pago_por_id(pago_id):
    return db.uno("SELECT * FROM pagos WHERE id = ?", [pago_id])


def pagos_de_grupo(grupo_id):
    return db.consultar(
        "SELECT pa.*, COALESCE(u1.nombre, m1.nombre_invitado, 'Alguien') AS de_nombre, "
        "COALESCE(u2.nombre, m2.nombre_invitado, 'Alguien') AS a_nombre "
        "FROM pagos pa JOIN miembros m1 ON m1.id = pa.de_miembro_id "
        "LEFT JOIN usuarios u1 ON u1.id = m1.usuario_id "
        "JOIN miembros m2 ON m2.id = pa.a_miembro_id "
        "LEFT JOIN usuarios u2 ON u2.id = m2.usuario_id "
        "WHERE pa.grupo_id = ? ORDER BY pa.fecha DESC, pa.id DESC", [grupo_id])


def borrar_pago(pago_id):
    return db.ejecutar("DELETE FROM pagos WHERE id = ?", [pago_id])


# ===========================================================================
# SALDOS: una sola consulta suma todo lo que mueve dinero en el grupo
#   + lo que pagó la persona      - lo que le toca de cada gasto
#   + lo que ya pagó a otros      - lo que ya le pagaron
# Positivo = le deben. Negativo = debe.
# ===========================================================================
def saldos_de_grupo(grupo_id):
    filas = db.consultar(
        "SELECT mid, SUM(valor) AS saldo FROM ("
        " SELECT pagado_por_id AS mid, monto AS valor FROM gastos WHERE grupo_id = ?"
        " UNION ALL"
        " SELECT p.miembro_id AS mid, -p.monto AS valor FROM participaciones p"
        "  JOIN gastos ga ON ga.id = p.gasto_id WHERE ga.grupo_id = ?"
        " UNION ALL"
        " SELECT de_miembro_id AS mid, monto AS valor FROM pagos WHERE grupo_id = ?"
        " UNION ALL"
        " SELECT a_miembro_id AS mid, -monto AS valor FROM pagos WHERE grupo_id = ?"
        ") movimientos GROUP BY mid",
        [grupo_id] * 4)
    return {f["mid"]: int(f["saldo"]) for f in filas}


# ===========================================================================
# INVITACIONES
# ===========================================================================
SELECT_INVITACION = (
    "SELECT i.*, gr.nombre AS grupo_nombre, gr.emoji AS grupo_emoji, "
    "u.nombre AS invitado_por_nombre "
    "FROM invitaciones i JOIN grupos gr ON gr.id = i.grupo_id "
    "LEFT JOIN usuarios u ON u.id = i.invitado_por_id "
)


def crear_invitacion(grupo_id, invitado_por_id, email, miembro_id, token):
    return db.insertar(
        "INSERT INTO invitaciones (grupo_id, invitado_por_id, email, miembro_id, token, estado, creado_en) "
        "VALUES (?, ?, ?, ?, ?, 'pendiente', ?)",
        [grupo_id, invitado_por_id, email, miembro_id, token, ahora()],
    )


def invitacion_por_id(invitacion_id):
    return db.uno(SELECT_INVITACION + "WHERE i.id = ?", [invitacion_id])


def invitacion_por_token(token):
    return db.uno(SELECT_INVITACION + "WHERE i.token = ?", [token])


def invitaciones_pendientes_de_grupo(grupo_id):
    return db.consultar(SELECT_INVITACION + "WHERE i.grupo_id = ? AND i.estado = 'pendiente' ORDER BY i.id DESC",
                        [grupo_id])


def invitaciones_de_email(email, estado=None, limite=20):
    if estado:
        return db.consultar(SELECT_INVITACION + "WHERE i.email = ? AND i.estado = ? ORDER BY i.id DESC LIMIT ?",
                            [email, estado, limite])
    return db.consultar(SELECT_INVITACION + "WHERE i.email = ? AND i.estado <> 'pendiente' "
                        "ORDER BY i.id DESC LIMIT ?", [email, limite])


def contar_invitaciones_pendientes(email):
    return db.valor("SELECT COUNT(*) FROM invitaciones WHERE email = ? AND estado = 'pendiente'",
                    [email], defecto=0)


def invitacion_pendiente_para(grupo_id, email):
    return db.uno("SELECT * FROM invitaciones WHERE grupo_id = ? AND email = ? AND estado = 'pendiente'",
                  [grupo_id, email])


def cerrar_invitacion(invitacion_id, estado):
    return db.ejecutar("UPDATE invitaciones SET estado = ?, respondido_en = ? WHERE id = ?",
                       [estado, ahora(), invitacion_id])


# ===========================================================================
# ACTIVIDAD (historial del grupo)
# ===========================================================================
def registrar_actividad(grupo_id, usuario_id, texto):
    return db.insertar("INSERT INTO actividad (grupo_id, usuario_id, texto, creado_en) VALUES (?, ?, ?, ?)",
                       [grupo_id, usuario_id, texto[:250], ahora()])


def actividad_de_grupo(grupo_id, limite=40):
    return db.consultar(
        "SELECT a.*, u.nombre AS autor, u.emoji AS autor_emoji FROM actividad a "
        "LEFT JOIN usuarios u ON u.id = a.usuario_id WHERE a.grupo_id = ? "
        "ORDER BY a.id DESC LIMIT ?", [grupo_id, limite])


def actividad_reciente(grupo_ids, limite=8):
    if not grupo_ids:
        return []
    return db.consultar(
        "SELECT a.*, u.nombre AS autor, u.emoji AS autor_emoji, gr.nombre AS grupo_nombre "
        "FROM actividad a JOIN grupos gr ON gr.id = a.grupo_id "
        f"LEFT JOIN usuarios u ON u.id = a.usuario_id WHERE a.grupo_id IN ({_marcadores(len(grupo_ids))}) "
        "ORDER BY a.id DESC LIMIT ?", [*grupo_ids, limite])


# ===========================================================================
# MENSAJES DEL FORMULARIO DE CONTACTO
# ===========================================================================
def crear_mensaje(nombre, email, texto):
    return db.insertar("INSERT INTO mensajes (nombre, email, texto, creado_en) VALUES (?, ?, ?, ?)",
                       [nombre, email, texto, ahora()])


def listar_mensajes(limite=15, desplazamiento=0):
    return db.consultar("SELECT * FROM mensajes ORDER BY id DESC LIMIT ? OFFSET ?", [limite, desplazamiento])


def contar_mensajes():
    return db.valor("SELECT COUNT(*) FROM mensajes", defecto=0)


def contar_mensajes_sin_leer():
    return db.valor("SELECT COUNT(*) FROM mensajes WHERE leido = 0", defecto=0)


def marcar_mensaje(mensaje_id, leido):
    return db.ejecutar("UPDATE mensajes SET leido = ? WHERE id = ?", [1 if leido else 0, mensaje_id])


def borrar_mensaje(mensaje_id):
    return db.ejecutar("DELETE FROM mensajes WHERE id = ?", [mensaje_id])


# ===========================================================================
# ESTADÍSTICAS PARA EL PANEL DE ADMINISTRACIÓN
# ===========================================================================
def estadisticas():
    return {
        "usuarios": contar_usuarios(),
        "admins": contar_admins(),
        "grupos": contar_grupos(),
        "gastos": db.valor("SELECT COUNT(*) FROM gastos", defecto=0),
        "total_gastado": int(db.valor("SELECT COALESCE(SUM(monto), 0) FROM gastos", defecto=0)),
        "pagos": db.valor("SELECT COUNT(*) FROM pagos", defecto=0),
        "invitaciones_pendientes": db.valor(
            "SELECT COUNT(*) FROM invitaciones WHERE estado = 'pendiente'", defecto=0),
        "mensajes_sin_leer": contar_mensajes_sin_leer(),
    }


# ===========================================================================
# COMENTARIOS (chat del grupo: gasto_id es NULL; comentarios de un gasto: gasto_id)
# ===========================================================================
def crear_comentario(grupo_id, usuario_id, texto, gasto_id=None):
    return db.insertar(
        "INSERT INTO comentarios (grupo_id, gasto_id, usuario_id, texto, creado_en) VALUES (?, ?, ?, ?, ?)",
        [grupo_id, gasto_id, usuario_id, texto, ahora()])


_SELECT_COMENTARIO = ("SELECT c.*, u.nombre AS autor, u.emoji AS autor_emoji FROM comentarios c "
                      "LEFT JOIN usuarios u ON u.id = c.usuario_id ")


def mensajes_de_chat(grupo_id, limite=60):
    return db.consultar(_SELECT_COMENTARIO + "WHERE c.grupo_id = ? AND c.gasto_id IS NULL "
                        "ORDER BY c.id DESC LIMIT ?", [grupo_id, limite])


def comentarios_de_gasto(gasto_id):
    return db.consultar(_SELECT_COMENTARIO + "WHERE c.gasto_id = ? ORDER BY c.id ASC", [gasto_id])


def comentario_por_id(comentario_id):
    return db.uno("SELECT * FROM comentarios WHERE id = ?", [comentario_id])


def borrar_comentario(comentario_id):
    return db.ejecutar("DELETE FROM comentarios WHERE id = ?", [comentario_id])
