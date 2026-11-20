import re
from app import db
from conftest import token, registrar


def test_paginas_publicas(cliente):
    for url in ["/", "/ayuda", "/contacto", "/desarrolladores", "/entrar", "/registro", "/api/salud"]:
        assert cliente.get(url).status_code == 200


def test_404_y_json_en_api(cliente):
    assert cliente.get("/no-existe").status_code == 404
    r = cliente.get("/api/yo")
    assert r.status_code == 401 and r.is_json


def test_rutas_privadas_piden_sesion(cliente):
    r = cliente.get("/panel")
    assert r.status_code == 302 and "/entrar" in r.headers["Location"]


def test_post_sin_csrf_es_rechazado(cliente):
    r = cliente.post("/registro", data={"nombre": "X", "email": "x@x.co", "clave": "Clave1234", "clave2": "Clave1234"})
    assert r.status_code in (400, 403)


def test_registro_valida_y_guarda_hash(app, cliente):
    r = registrar(cliente, "Ana", "ana@x.co", "corta")
    assert r.status_code == 200  # vuelve al formulario con errores
    assert registrar(cliente, "Ana", "ana@x.co").status_code == 302
    with app.app_context():
        fila = db.conexion().execute("SELECT password_hash FROM usuarios WHERE email='ana@x.co'").fetchone()
        assert "Clave1234" not in fila[0]


def test_login_y_logout(app, ana):
    ana.post("/salir", data={"csrf_token": token(ana, "/perfil")})
    assert ana.get("/panel").status_code == 302
    r = ana.post("/entrar", data={"csrf_token": token(ana), "email": "ana@x.co", "clave": "mala"})
    assert r.status_code == 200
    r = ana.post("/entrar", data={"csrf_token": token(ana), "email": "ana@x.co", "clave": "Clave1234"})
    assert r.status_code == 302


def test_usuario_normal_no_entra_al_admin(ana):
    assert ana.get("/admin/").status_code == 403
    assert ana.get("/admin/usuarios").status_code == 403


def test_flujo_grupo_gasto_invitacion(app, ana):
    r = ana.post("/grupos/nuevo", data={"csrf_token": token(ana, "/grupos/nuevo"), "nombre": "Viaje",
                                        "emoji": "🏖️", "invitados": "Carlos"})
    gid = int(re.search(r"/grupos/(\d+)", r.headers["Location"]).group(1))
    t = token(ana, f"/grupos/{gid}/gastos/nuevo")
    r = ana.post(f"/grupos/{gid}/gastos/nuevo", data={
        "csrf_token": t, "descripcion": "Cena", "monto": "100.000", "categoria": "comida",
        "pagado_por": "1", "tipo_division": "igual", "participantes": ["1", "2"]})
    assert r.status_code == 302
    html = ana.get(f"/grupos/{gid}?vista=saldos").data.decode()
    assert "$50.000" in html

    beto = app.test_client()
    registrar(beto, "Beto", "beto@x.co")
    ana.post(f"/grupos/{gid}/invitar", data={"csrf_token": t, "email": "beto@x.co"})
    bandeja = beto.get("/invitaciones").data.decode()
    iid = re.search(r"/invitaciones/(\d+)/aceptar", bandeja).group(1)
    assert beto.post(f"/invitaciones/{iid}/aceptar", data={"csrf_token": token(beto, "/invitaciones")}).status_code == 302
    assert beto.get(f"/grupos/{gid}").status_code == 200


def test_gasto_invalido_muestra_errores(ana):
    ana.post("/grupos/nuevo", data={"csrf_token": token(ana, "/grupos/nuevo"), "nombre": "Grupo", "emoji": "🏖️"})
    r = ana.post("/grupos/1/gastos/nuevo", data={"csrf_token": token(ana, "/grupos/1/gastos/nuevo"),
                                                  "descripcion": "", "monto": "abc"})
    assert r.status_code == 200


def test_otro_usuario_no_ve_grupo_ajeno(app, ana):
    ana.post("/grupos/nuevo", data={"csrf_token": token(ana, "/grupos/nuevo"), "nombre": "Privado", "emoji": "🏖️"})
    otro = app.test_client()
    registrar(otro, "Otro", "otro@x.co")
    assert otro.get("/grupos/1").status_code in (403, 404)


def test_api_con_token(app, ana):
    ana.post("/perfil/token", data={"csrf_token": token(ana, "/perfil")})
    html = ana.get("/perfil").data.decode()
    m = re.search(r"(sf_[A-Za-z0-9_\-]+)", html)
    assert m, "el token nuevo debe mostrarse una vez"
    api = app.test_client()
    r = api.get("/api/yo", headers={"Authorization": f"Bearer {m.group(1)}"})
    assert r.status_code == 200 and r.get_json()["email"] == "ana@x.co"


def test_chat_y_comentarios(app, ana):
    ana.post("/grupos/nuevo", data={"csrf_token": token(ana, "/grupos/nuevo"), "nombre": "Grupo", "emoji": "🏖️"})
    t = token(ana, "/grupos/1/gastos/nuevo")
    ana.post("/grupos/1/gastos/nuevo", data={"csrf_token": t, "descripcion": "Cena", "monto": "40000",
             "categoria": "comida", "pagado_por": "1", "tipo_division": "igual", "participantes": ["1"]})
    # chat
    ana.post("/grupos/1/chat", data={"csrf_token": t, "texto": "Hola <b>a todos</b>"})
    html = ana.get("/grupos/1?vista=chat").data.decode()
    assert "Hola &lt;b&gt;a todos&lt;/b&gt;" in html  # se escapa el HTML
    # vacío y muy largo se rechazan
    ana.post("/grupos/1/chat", data={"csrf_token": t, "texto": "   "})
    ana.post("/grupos/1/chat", data={"csrf_token": t, "texto": "x" * 501})
    assert ana.get("/grupos/1?vista=chat").data.decode().count('class="mensaje ') == 1
    # comentario en gasto
    r = ana.post("/grupos/1/gastos/1/comentarios", data={"csrf_token": t, "texto": "Yo no tomé licor"})
    assert r.status_code == 302
    assert "Yo no tomé licor" in ana.get("/grupos/1/gastos/1").data.decode()
    assert "💬" in ana.get("/grupos/1").data.decode()
    # un extraño no puede leer ni escribir
    otro = app.test_client()
    registrar(otro, "Otro", "otro@x.co")
    assert otro.get("/grupos/1/gastos/1").status_code == 403
    assert otro.post("/grupos/1/chat", data={"csrf_token": token(otro, "/grupos/nuevo"), "texto": "hola"}).status_code == 403
    # el autor puede borrar
    assert ana.post("/grupos/1/comentarios/1/eliminar", data={"csrf_token": t}).status_code == 302
