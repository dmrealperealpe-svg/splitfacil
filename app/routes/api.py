"""API REST de SplitFácil (Tema 6): JSON, endpoints, verbos HTTP y códigos de respuesta.

Cómo se autentica quien la usa:
  · Con un token personal (se crea en Perfil → Acceso por API):
        Authorization: Bearer sf_xxxxxxxx
  · O con la sesión del navegador. En ese caso, los POST/DELETE también envían la cabecera
    X-CSRF-Token, igual que los formularios.

Todos los errores salen en JSON: {"error": "...", "detalle": "..."}.
"""
from functools import wraps

from flask import Blueprint, abort, g, jsonify, request, url_for
from werkzeug.datastructures import MultiDict

from .. import datos, db, servicios
from ..utilidades import CATEGORIAS, cop

bp = Blueprint("api", __name__, url_prefix="/api")

VERSION = "1.0"


# ---------------------------------------------------------------------------
# Autenticación y utilidades
# ---------------------------------------------------------------------------
def _usuario_api():
    cabecera = request.headers.get("Authorization", "")
    if cabecera.startswith("Bearer "):
        return servicios.usuario_por_token_api(cabecera[7:].strip())
    return g.user  # sesión del navegador


def api_login(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = _usuario_api()
        if usuario is None:
            respuesta = jsonify(error="No autenticado",
                                detalle="Envía tu token en la cabecera Authorization: Bearer <token> "
                                        "o inicia sesión en el navegador.")
            respuesta.status_code = 401
            respuesta.headers["WWW-Authenticate"] = "Bearer"
            return respuesta
        g.api_user = usuario
        return vista(*args, **kwargs)
    return envoltura


@bp.after_request
def sin_cache(respuesta):
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


def _grupo_y_yo(grupo_id):
    grupo = datos.grupo_por_id(grupo_id)
    if grupo is None:
        abort(404)
    yo = datos.miembro_de_usuario(grupo_id, g.api_user["id"])
    if yo is None:
        abort(403)
    return grupo, yo


def _entero(nombre, defecto, minimo, maximo):
    try:
        return max(minimo, min(maximo, int(request.args.get(nombre, defecto))))
    except ValueError:
        return defecto


def _miembro_json(m):
    return {"id": m["id"], "nombre": m["nombre"], "tiene_cuenta": m["tiene_cuenta"],
            "es_propietario": bool(m["es_propietario"])}


def _gasto_json(f):
    etiqueta, _emoji = CATEGORIAS.get(f["categoria"], CATEGORIAS["otros"])
    return {"id": f["id"], "descripcion": f["descripcion"], "monto": f["monto"], "monto_texto": cop(f["monto"]),
            "categoria": f["categoria"], "categoria_nombre": etiqueta, "fecha": f["fecha"],
            "pagado_por": {"id": f["pagado_por_id"], "nombre": f["pagador"]},
            "tipo_division": f["tipo_division"], "nota": f["nota"],
            "n_participantes": f.get("n_participantes"), "tu_parte": f.get("mi_parte")}


# ---------------------------------------------------------------------------
# Endpoints públicos
# ---------------------------------------------------------------------------
@bp.get("/")
def indice():
    return jsonify(nombre="SplitFácil API", version=VERSION, documentacion=url_for("principal.desarrolladores"),
                   endpoints=["GET /api/salud", "GET /api/categorias", "GET /api/yo", "GET /api/grupos",
                              "GET /api/grupos/<id>", "GET /api/grupos/<id>/gastos",
                              "POST /api/grupos/<id>/gastos", "GET /api/grupos/<id>/gastos/<id>",
                              "DELETE /api/grupos/<id>/gastos/<id>", "GET /api/grupos/<id>/saldos"])


@bp.get("/salud")
def salud():
    """Para que el servidor (Render, etc.) compruebe que la app y la base de datos responden."""
    db.valor("SELECT 1")
    return jsonify(estado="ok", version=VERSION)


@bp.get("/categorias")
def categorias():
    return jsonify([{"clave": clave, "nombre": nombre, "emoji": emoji}
                    for clave, (nombre, emoji) in CATEGORIAS.items()])


# ---------------------------------------------------------------------------
# Endpoints privados
# ---------------------------------------------------------------------------
@bp.get("/yo")
@api_login
def yo():
    u = g.api_user
    return jsonify(id=u["id"], nombre=u["nombre"], email=u["email"], es_admin=bool(u["es_admin"]),
                   creado_en=u["creado_en"])


@bp.get("/grupos")
@api_login
def grupos():
    tarjetas, te_deben, debes = servicios.resumen_usuario(g.api_user["id"])
    return jsonify(te_deben=te_deben, debes=debes, grupos=[
        {"id": t["id"], "nombre": t["nombre"], "descripcion": t["descripcion"], "emoji": t["emoji"],
         "n_miembros": t["n_miembros"], "n_gastos": t["n_gastos"], "tu_saldo": t["saldo"],
         "soy_propietario": bool(t["soy_propietario"])} for t in tarjetas])


@bp.get("/grupos/<int:grupo_id>")
@api_login
def grupo(grupo_id):
    gr, yo_ = _grupo_y_yo(grupo_id)
    miembros = datos.miembros_de_grupo(grupo_id)
    saldos = servicios.saldos(grupo_id, miembros)
    return jsonify(id=gr["id"], nombre=gr["nombre"], descripcion=gr["descripcion"], emoji=gr["emoji"],
                   total_gastado=datos.total_gastado(grupo_id), n_gastos=datos.contar_gastos(grupo_id),
                   tu_miembro_id=yo_["id"], tu_saldo=saldos.get(yo_["id"], 0),
                   miembros=[_miembro_json(m) for m in miembros])


@bp.get("/grupos/<int:grupo_id>/gastos")
@api_login
def gastos(grupo_id):
    _gr, yo_ = _grupo_y_yo(grupo_id)
    texto = request.args.get("q", "").strip()[:60]
    categoria = request.args.get("categoria", "")
    if categoria not in CATEGORIAS:
        categoria = ""
    por_pagina = _entero("por_pagina", 20, 1, 50)
    pagina = _entero("pagina", 1, 1, 10_000)
    total = datos.contar_gastos(grupo_id, texto, categoria)
    filas = datos.gastos_de_grupo(grupo_id, yo_["id"], texto, categoria, por_pagina, (pagina - 1) * por_pagina)
    return jsonify(total=total, pagina=pagina, por_pagina=por_pagina, gastos=[_gasto_json(f) for f in filas])


@bp.get("/grupos/<int:grupo_id>/gastos/<int:gasto_id>")
@api_login
def gasto(grupo_id, gasto_id):
    _gr, yo_ = _grupo_y_yo(grupo_id)
    gasto_ = datos.gasto_por_id(gasto_id)
    if gasto_ is None or gasto_["grupo_id"] != grupo_id:
        abort(404)
    por_id = {m["id"]: m["nombre"] for m in datos.miembros_de_grupo(grupo_id)}
    datos_gasto = _gasto_json({**gasto_, "pagador": por_id.get(gasto_["pagado_por_id"], "Alguien")})
    datos_gasto["reparto"] = [{"miembro_id": mid, "nombre": por_id.get(mid, "Alguien"), "monto": monto}
                              for mid, monto in datos.participaciones_de_gasto(gasto_id).items()]
    return jsonify(datos_gasto)


def _form_desde_json(cuerpo, miembros):
    """Convierte el JSON recibido al mismo formato que usan los formularios, para reutilizar la validación."""
    form = MultiDict()
    for clave in ("descripcion", "monto", "categoria", "fecha", "pagado_por", "tipo_division", "nota"):
        if cuerpo.get(clave) is not None:
            form[clave] = str(cuerpo[clave])
    participantes = cuerpo.get("participantes")
    if participantes is None:  # si no dices quién comparte el gasto, se reparte entre todo el grupo
        participantes = [m["id"] for m in miembros]
    for miembro_id in participantes if isinstance(participantes, list) else []:
        form.add("participantes", str(miembro_id))
    partes = cuerpo.get("partes")
    for miembro_id, monto in (partes.items() if isinstance(partes, dict) else []):
        form[f"parte_{miembro_id}"] = str(monto)
    return form


@bp.post("/grupos/<int:grupo_id>/gastos")
@api_login
def gasto_crear(grupo_id):
    gr, yo_ = _grupo_y_yo(grupo_id)
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return jsonify(error="JSON no válido", detalle="Envía un objeto JSON con Content-Type: application/json."), 400
    miembros = datos.miembros_de_grupo(grupo_id)
    cuerpo.setdefault("pagado_por", yo_["id"])
    campos, errores = servicios.validar_gasto(miembros, _form_desde_json(cuerpo, miembros))
    if errores:
        return jsonify(error="Datos no válidos", errores=errores), 422
    gasto_id = servicios.guardar_gasto(gr, g.api_user, campos)
    respuesta = jsonify(id=gasto_id, descripcion=campos["descripcion"], monto=campos["monto"],
                        reparto=[{"miembro_id": mid, "monto": monto} for mid, monto in campos["partes"].items()])
    respuesta.status_code = 201
    respuesta.headers["Location"] = url_for("api.gasto", grupo_id=grupo_id, gasto_id=gasto_id)
    return respuesta


@bp.delete("/grupos/<int:grupo_id>/gastos/<int:gasto_id>")
@api_login
def gasto_borrar(grupo_id, gasto_id):
    gr, yo_ = _grupo_y_yo(grupo_id)
    gasto_ = datos.gasto_por_id(gasto_id)
    if gasto_ is None or gasto_["grupo_id"] != grupo_id:
        abort(404)
    if not servicios.puede_modificar(gasto_, g.api_user, yo_):
        abort(403)
    datos.borrar_gasto(gasto_id)
    servicios.registrar(grupo_id, g.api_user, f"eliminó el gasto «{gasto_['descripcion']}» ({cop(gasto_['monto'])})")
    db.confirmar()
    return "", 204


@bp.get("/grupos/<int:grupo_id>/saldos")
@api_login
def saldos(grupo_id):
    _gr, yo_ = _grupo_y_yo(grupo_id)
    miembros = datos.miembros_de_grupo(grupo_id)
    por_id = {m["id"]: m for m in miembros}
    s = servicios.saldos(grupo_id, miembros)
    return jsonify(
        tu_miembro_id=yo_["id"],
        saldos=[{"miembro_id": m["id"], "nombre": m["nombre"], "saldo": s[m["id"]]} for m in miembros],
        para_saldar=[{"de": {"id": d, "nombre": por_id[d]["nombre"]}, "a": {"id": a, "nombre": por_id[a]["nombre"]},
                      "monto": monto} for d, a, monto in servicios.deudas_sugeridas(s)])
