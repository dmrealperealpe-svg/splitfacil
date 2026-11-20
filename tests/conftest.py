import re
import pytest
from app import create_app, db


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("APP_ENV", "testing")
    return create_app()


@pytest.fixture()
def cliente(app):
    return app.test_client()


def token(c, url="/entrar"):
    html = c.get(url).data.decode()
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def registrar(c, nombre, email, clave="Clave1234"):
    return c.post("/registro", data={"csrf_token": token(c, "/registro"), "nombre": nombre,
                                     "email": email, "clave": clave, "clave2": clave})


@pytest.fixture()
def ana(app):
    c = app.test_client()
    registrar(c, "Ana Pérez", "ana@x.co")
    return c
