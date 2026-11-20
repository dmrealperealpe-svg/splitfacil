"""Reglas de negocio de SplitFácil.

Las rutas (routes/*.py) reciben la petición; este archivo decide qué es válido
y qué se guarda; datos.py ejecuta el SQL. Cada capa hace una sola cosa.
"""
import hashlib
import re
import secrets
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from . import datos, db
from .utilidades import CATEGORIAS, cop, email_valido, hoy_local, parse_monto

TIPOS_DIVISION = ("igual", "exacta")


# ---------------------------------------------------------------------------
# Cuentas
# ---------------------------------------------------------------------------
def hash_clave(clave):
    return generate_password_hash(clave)


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def generar_token_api(usuario):
    """Crea un token nuevo; solo guardamos su huella (hash), nunca el token."""
    token = "sf_" + secrets.token_urlsafe(32)
    datos.actualizar_usuario(usuario["id"], token_api_hash=hash_token(token))
    db.confirmar()
    return token


def revocar_token_api(usuario):
    datos.actualizar_usuario(usuario["id"], token_api_hash=None)
    db.confirmar()


def usuario_por_token_api(token):
    return datos.usuario_por_token(hash_token(token)) if token else None


def eliminar_cuenta(usuario):
    """Borra la cuenta conservando el historial de los grupos de otras personas."""
    for membresia in datos.membresias_de_usuario(usuario["id"]):
        miembros = datos.miembros_de_grupo(membresia["grupo_id"])
        otros = [m for m in miembros if m["usuario_id"] not in (None, usuario["id"])]
        if not otros:
            datos.borrar_grupo(membresia["grupo_id"])  # nadie más lo usa
            continue
        if membresia["es_propietario"]:
            datos.actualizar_miembro(otros[0]["id"], es_propietario=1)
        # La persona queda en el historial como "invitado" con su nombre.
        datos.actualizar_miembro(membresia["id"], nombre_invitado=usuario["nombre"], es_propietario=0)
    datos.borrar_usuario(usuario["id"])  # las llaves foráneas ON DELETE SET NULL hacen el resto
    db.confirmar()


# ---------------------------------------------------------------------------
# Dinero: dividir y calcular saldos
# ---------------------------------------------------------------------------
def dividir_igual(monto, ids):
    """Reparte `monto` entre `ids` sin perder ni un peso: 100 entre 3 -> 34, 33, 33."""
    ids = sorted(ids)
    base, resto = divmod(monto, len(ids))
    return {mid: base + (1 if i < resto else 0) for i, mid in enumerate(ids)}


def saldos(grupo_id, miembros):
    """{miembro_id: saldo}. Positivo = le deben. Negativo = debe."""
    resultado = {m["id"]: 0 for m in miembros}
    resultado.update({mid: s for mid, s in datos.saldos_de_grupo(grupo_id).items() if mid in resultado})
    return resultado


def deudas_sugeridas(saldos_):
    """Pocos pagos que dejan todo en cero. Devuelve [(deudor_id, acreedor_id, monto)]."""
    deudores = sorted(([m, -s] for m, s in saldos_.items() if s < 0), key=lambda x: (-x[1], x[0]))
    acreedores = sorted(([m, s] for m, s in saldos_.items() if s > 0), key=lambda x: (-x[1], x[0]))
    pagos, i, j = [], 0, 0
    while i < len(deudores) and j < len(acreedores):
        monto = min(deudores[i][1], acreedores[j][1])
        pagos.append((deudores[i][0], acreedores[j][0], monto))
        deudores[i][1] -= monto
        acreedores[j][1] -= monto
        if deudores[i][1] == 0:
            i += 1
        if acreedores[j][1] == 0:
            j += 1
    return pagos


def resumen_por_categoria(grupo_id):
    filas = datos.resumen_categorias(grupo_id)
    total = sum(f["total"] for f in filas) or 1
    resultado = []
    for f in filas:
        etiqueta, emoji = CATEGORIAS.get(f["categoria"], CATEGORIAS["otros"])
        resultado.append({"clave": f["categoria"], "etiqueta": etiqueta, "emoji": emoji,
                          "total": f["total"], "n": f["n"], "porcentaje": round(f["total"] * 100 / total)})
    return resultado


def resumen_usuario(usuario_id):
    """Para el panel: tarjetas por grupo y totales de lo que te deben y debes."""
    tarjetas, te_deben, debes = [], 0, 0
    for grupo in datos.grupos_de_usuario(usuario_id):
        saldo = datos.saldos_de_grupo(grupo["id"]).get(grupo["mi_miembro_id"], 0)
        tarjetas.append({**grupo, "saldo": saldo})
        if saldo > 0:
            te_deben += saldo
        else:
            debes += -saldo
    return tarjetas, te_deben, debes


def registrar(grupo_id, usuario, texto):
    datos.registrar_actividad(grupo_id, usuario["id"] if usuario else None, texto)


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------
def separar_nombres(texto, excluir=()):
    vistos = {n.lower() for n in excluir}
    nombres = []
    for bruto in re.split(r"[,;\n]", texto or ""):
        nombre = " ".join(bruto.split())[:80]
        if nombre and nombre.lower() not in vistos:
            vistos.add(nombre.lower())
            nombres.append(nombre)
    return nombres[:30]


def validar_grupo(form, emojis):
    errores = {}
    nombre = " ".join(form.get("nombre", "").split())
    descripcion = form.get("descripcion", "").strip()[:200]
    emoji = form.get("emoji", emojis[0])
    if emoji not in emojis:
        emoji = emojis[0]
    if len(nombre) < 2:
        errores["nombre"] = "Ponle un nombre al grupo (mínimo 2 letras)."
    elif len(nombre) > 80:
        errores["nombre"] = "El nombre es demasiado largo (máximo 80)."
    return {"nombre": nombre, "descripcion": descripcion, "emoji": emoji}, errores


def crear_grupo(usuario, campos, invitados_texto):
    grupo_id = datos.crear_grupo(campos["nombre"], campos["descripcion"], campos["emoji"], usuario["id"])
    datos.crear_miembro(grupo_id, usuario_id=usuario["id"], es_propietario=1)
    for nombre in separar_nombres(invitados_texto, excluir=[usuario["nombre"]]):
        datos.crear_miembro(grupo_id, nombre_invitado=nombre)
    registrar(grupo_id, usuario, "creó el grupo")
    db.confirmar()
    return grupo_id


def agregar_invitado(grupo, usuario, nombre):
    nombre = " ".join((nombre or "").split())[:80]
    if not nombre:
        return False, "Escribe el nombre de la persona."
    if nombre.lower() in [m["nombre"].lower() for m in datos.miembros_de_grupo(grupo["id"])]:
        return False, "Ya hay alguien con ese nombre en el grupo."
    datos.crear_miembro(grupo["id"], nombre_invitado=nombre)
    registrar(grupo["id"], usuario, f"agregó a {nombre} (sin cuenta)")
    db.confirmar()
    return True, f"Agregaste a {nombre} al grupo."


def quitar_miembro(grupo, miembro, usuario):
    if miembro["es_propietario"]:
        return False, "El propietario no se puede quitar. Transfiere la propiedad o elimina el grupo."
    nombre = miembro["nombre"]
    if datos.miembro_tiene_movimientos(miembro["id"]):
        if not miembro["tiene_cuenta"]:
            return False, f"{nombre} tiene gastos o pagos registrados. Elimínalos primero si quieres quitarlo."
        datos.actualizar_miembro(miembro["id"], usuario_id=None, nombre_invitado=nombre)
        mensaje = f"{nombre} ya no tiene acceso al grupo. Sus gastos se conservan en el historial."
    else:
        datos.borrar_miembro(miembro["id"])
        mensaje = f"Quitaste a {nombre} del grupo."
    registrar(grupo["id"], usuario, f"quitó a {nombre} del grupo")
    db.confirmar()
    return True, mensaje


def salir_del_grupo(grupo, miembro, usuario):
    if miembro["es_propietario"]:
        return False, "Eres el propietario: transfiere la propiedad a otra persona o elimina el grupo."
    saldo = datos.saldos_de_grupo(grupo["id"]).get(miembro["id"], 0)
    if saldo != 0:
        return False, f"Antes de salir, salda tus cuentas ({cop(abs(saldo))} pendientes)."
    if datos.miembro_tiene_movimientos(miembro["id"]):
        datos.actualizar_miembro(miembro["id"], usuario_id=None, nombre_invitado=usuario["nombre"])
    else:
        datos.borrar_miembro(miembro["id"])
    registrar(grupo["id"], usuario, "salió del grupo")
    db.confirmar()
    return True, f"Saliste de «{grupo['nombre']}»."


def transferir_propiedad(grupo, actual, destino, usuario):
    if not destino["tiene_cuenta"] or destino["id"] == actual["id"]:
        return False, "Solo puedes transferir la propiedad a otra persona con cuenta."
    datos.actualizar_miembro(actual["id"], es_propietario=0)
    datos.actualizar_miembro(destino["id"], es_propietario=1)
    registrar(grupo["id"], usuario, f"hizo propietario a {destino['nombre']}")
    db.confirmar()
    return True, f"{destino['nombre']} ahora es propietario del grupo."


# ---------------------------------------------------------------------------
# Gastos
# ---------------------------------------------------------------------------
def _fecha_valida(texto):
    try:
        datetime.strptime(texto, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validar_gasto(miembros, form):
    """Devuelve (datos_limpios, errores). `form` puede ser request.form o un MultiDict."""
    errores = {}
    ids_validos = {m["id"] for m in miembros}

    descripcion = " ".join(form.get("descripcion", "").split())
    if not descripcion:
        errores["descripcion"] = "Escribe en qué se gastó."
    elif len(descripcion) > 120:
        errores["descripcion"] = "La descripción es demasiado larga (máximo 120)."

    monto = parse_monto(form.get("monto", ""))
    if monto is None:
        errores["monto"] = "El monto debe ser un número mayor a 0 (máximo 1.000.000.000)."

    categoria = form.get("categoria", "otros")
    if categoria not in CATEGORIAS:
        categoria = "otros"

    fecha = form.get("fecha", "").strip() or hoy_local()
    if not _fecha_valida(fecha):
        errores["fecha"] = "La fecha no es válida."

    try:
        pagado_por = int(form.get("pagado_por", ""))
    except (TypeError, ValueError):
        pagado_por = None
    if pagado_por not in ids_validos:
        errores["pagado_por"] = "Elige quién pagó."

    tipo = form.get("tipo_division", "igual")
    if tipo not in TIPOS_DIVISION:
        tipo = "igual"

    participantes = []
    for bruto in form.getlist("participantes"):
        if str(bruto).isdigit() and int(bruto) in ids_validos and int(bruto) not in participantes:
            participantes.append(int(bruto))
    if not participantes:
        errores["participantes"] = "Elige al menos una persona que comparta este gasto."

    partes = {}
    if participantes and monto:
        if tipo == "igual":
            partes = dividir_igual(monto, participantes)
        else:
            for miembro_id in participantes:
                valor = parse_monto(form.get(f"parte_{miembro_id}", ""), minimo=0)
                if valor is None:
                    errores["partes"] = "Revisa los montos de cada persona: deben ser números."
                    break
                if valor > 0:
                    partes[miembro_id] = valor
            if "partes" not in errores and sum(partes.values()) != monto:
                errores["partes"] = (f"Las partes suman {cop(sum(partes.values()))} "
                                     f"y el gasto es de {cop(monto)}. Deben ser iguales.")

    limpio = {"descripcion": descripcion, "monto": monto, "categoria": categoria, "fecha": fecha,
              "pagado_por": pagado_por, "tipo_division": tipo, "participantes": participantes,
              "partes": partes, "nota": form.get("nota", "").strip()[:300]}
    return limpio, errores


def guardar_gasto(grupo, usuario, campos, gasto_id=None):
    if gasto_id is None:
        gasto_id = datos.crear_gasto(grupo["id"], campos["descripcion"], campos["monto"], campos["categoria"],
                                     campos["fecha"], campos["pagado_por"], usuario["id"],
                                     campos["tipo_division"], campos["nota"])
        verbo = "agregó"
    else:
        datos.actualizar_gasto(gasto_id, campos["descripcion"], campos["monto"], campos["categoria"],
                               campos["fecha"], campos["pagado_por"], campos["tipo_division"], campos["nota"])
        verbo = "editó"
    datos.reemplazar_participaciones(gasto_id, campos["partes"])
    registrar(grupo["id"], usuario, f"{verbo} el gasto «{campos['descripcion']}» ({cop(campos['monto'])})")
    db.confirmar()
    return gasto_id


def puede_modificar(gasto_o_pago, usuario, yo):
    """Solo quien lo creó o el propietario del grupo puede editarlo o borrarlo."""
    return gasto_o_pago["creado_por_id"] == usuario["id"] or bool(yo["es_propietario"])


# ---------------------------------------------------------------------------
# Pagos entre personas del grupo
# ---------------------------------------------------------------------------
def validar_pago(miembros, form):
    errores = {}
    ids_validos = {m["id"] for m in miembros}

    def _id(campo):
        try:
            valor = int(form.get(campo, ""))
        except (TypeError, ValueError):
            return None
        return valor if valor in ids_validos else None

    de, a = _id("de"), _id("a")
    if de is None:
        errores["de"] = "Elige quién paga."
    if a is None:
        errores["a"] = "Elige quién recibe."
    if de is not None and de == a:
        errores["a"] = "Quien paga y quien recibe deben ser personas distintas."
    monto = parse_monto(form.get("monto", ""))
    if monto is None:
        errores["monto"] = "El monto debe ser un número mayor a 0."
    fecha = form.get("fecha", "").strip() or hoy_local()
    if not _fecha_valida(fecha):
        errores["fecha"] = "La fecha no es válida."
    return {"de": de, "a": a, "monto": monto, "fecha": fecha, "nota": form.get("nota", "").strip()[:200]}, errores


def guardar_pago(grupo, usuario, campos, miembros):
    datos.crear_pago(grupo["id"], campos["de"], campos["a"], campos["monto"], campos["fecha"],
                     campos["nota"], usuario["id"])
    nombres = {m["id"]: m["nombre"] for m in miembros}
    registrar(grupo["id"], usuario,
              f"registró un pago de {nombres[campos['de']]} a {nombres[campos['a']]} por {cop(campos['monto'])}")
    db.confirmar()


# ---------------------------------------------------------------------------
# Invitaciones
# ---------------------------------------------------------------------------
def crear_invitacion(grupo, usuario, email, miembro_id, miembros):
    """Con correo: la ve esa persona en su bandeja. Sin correo: genera un enlace de un solo uso."""
    email = (email or "").strip().lower()
    if email:
        if not email_valido(email):
            return None, "Escribe un correo válido, o déjalo vacío para crear un enlace."
        if any((m.get("email") or "") == email for m in miembros):
            return None, "Esa persona ya está en el grupo."
        if datos.invitacion_pendiente_para(grupo["id"], email):
            return None, "Ya hay una invitación pendiente para ese correo."
    vinculado = None
    if miembro_id:
        elegido = next((m for m in miembros if m["id"] == miembro_id and not m["tiene_cuenta"]), None)
        if elegido is None:
            return None, "Esa persona ya tiene cuenta o no está en el grupo."
        vinculado = elegido["id"]
    token = secrets.token_urlsafe(24)
    invitacion_id = datos.crear_invitacion(grupo["id"], usuario["id"], email or None, vinculado, token)
    registrar(grupo["id"], usuario, f"invitó a {email}" if email else "creó un enlace de invitación")
    db.confirmar()
    return datos.invitacion_por_id(invitacion_id), None


def puede_responder(invitacion, usuario):
    """Una invitación con correo solo la responde ese correo; una con enlace, cualquiera con cuenta."""
    return invitacion["email"] is None or invitacion["email"] == usuario["email"]


def aceptar_invitacion(invitacion, usuario):
    ya = datos.miembro_de_usuario(invitacion["grupo_id"], usuario["id"])
    if ya:
        datos.cerrar_invitacion(invitacion["id"], "aceptada")
        db.confirmar()
        return ya
    vinculado = datos.miembro_por_id(invitacion["miembro_id"]) if invitacion["miembro_id"] else None
    if vinculado and vinculado["grupo_id"] == invitacion["grupo_id"] and not vinculado["tiene_cuenta"]:
        # La persona "sin cuenta" del grupo ahora es este usuario: conserva todos sus gastos.
        datos.actualizar_miembro(vinculado["id"], usuario_id=usuario["id"], nombre_invitado=None)
        miembro_id = vinculado["id"]
    else:
        miembro_id = datos.crear_miembro(invitacion["grupo_id"], usuario_id=usuario["id"])
    datos.cerrar_invitacion(invitacion["id"], "aceptada")
    registrar(invitacion["grupo_id"], usuario, "se unió al grupo")
    db.confirmar()
    return datos.miembro_por_id(miembro_id)


def cerrar_invitacion(invitacion, estado):
    datos.cerrar_invitacion(invitacion["id"], estado)
    db.confirmar()


# ---------------------------------------------------------------------------
# Datos de ejemplo
# ---------------------------------------------------------------------------
def _gasto_demo(grupo_id, usuario, descripcion, monto, categoria, dias_atras, pagador_id, participantes):
    fecha = (datetime.strptime(hoy_local(), "%Y-%m-%d") - timedelta(days=dias_atras)).strftime("%Y-%m-%d")
    gasto_id = datos.crear_gasto(grupo_id, descripcion, monto, categoria, fecha, pagador_id,
                                 usuario["id"], "igual", "")
    datos.reemplazar_participaciones(gasto_id, dividir_igual(monto, participantes))


def crear_datos_demo(usuario):
    """Dos grupos de ejemplo para explorar la app sin escribir nada."""
    g1 = crear_grupo(usuario, {"nombre": "Apartamento 5B", "emoji": "🏠",
                               "descripcion": "Gastos de la casa compartida"}, "Camila, Jorge")
    m = {x["nombre"]: x["id"] for x in datos.miembros_de_grupo(g1)}
    todos = list(m.values())
    _gasto_demo(g1, usuario, "Arriendo del mes", 1200000, "hogar", 20, m["Camila"], todos)
    _gasto_demo(g1, usuario, "Mercado quincenal", 185000, "comida", 9, m[usuario["nombre"]], todos)
    _gasto_demo(g1, usuario, "Internet y servicios", 210000, "servicios", 5, m["Jorge"], todos)
    datos.crear_pago(g1, m["Jorge"], m["Camila"], 100000, hoy_local(), "Abono al arriendo", usuario["id"])

    g2 = crear_grupo(usuario, {"nombre": "Viaje a la costa", "emoji": "🏖️",
                               "descripcion": "Puente festivo con amigos"}, "Laura, Andrés, Camila")
    m = {x["nombre"]: x["id"] for x in datos.miembros_de_grupo(g2)}
    todos = list(m.values())
    _gasto_demo(g2, usuario, "Hospedaje 3 noches", 980000, "viajes", 12, m["Laura"], todos)
    _gasto_demo(g2, usuario, "Gasolina ida y vuelta", 260000, "transporte", 11, m[usuario["nombre"]], todos)
    _gasto_demo(g2, usuario, "Cena en el malecón", 145000, "comida", 10, m["Andrés"], todos)
    db.confirmar()
