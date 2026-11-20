"""Arranque para desarrollo.   Uso:  python run.py   y abre http://127.0.0.1:5000

En producción NO se usa este archivo: el servidor ejecuta wsgi.py con gunicorn (ver README).
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=app.config["DEBUG"])
